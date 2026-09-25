# Step 4: Team Proxy

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="../01-invisible-cost/" class="dt-trail-step inactive">Step 1: Invisible Cost</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../02-first-dev-span/" class="dt-trail-step inactive">Step 2: Bedrock Telemetry</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../03-claude-code-hook/" class="dt-trail-step inactive">Step 3: Harness Hooks</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 4: Enterprise Push</span>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../05-cost-attribution/" class="dt-trail-step inactive">Step 5: AI Gateway</a>
  </div>
</div>

A proxy is the most complete solution for observing developer AI usage: a lightweight server that all AI traffic routes through. Every call from every tool, every developer, becomes visible in one place.

## The architecture

Without a proxy, AI tools talk directly to Bedrock Mantle. You see nothing unless you've instrumented each tool individually.

With a proxy, the flow is:

```
AI tool → proxy (localhost or team endpoint) → Bedrock Mantle
```

The proxy is OpenAI-compatible. AI tools that support a custom base URL, including Claude Code, Cursor, and any script using the OpenAI client, can be pointed at it with one configuration change per developer (or pushed via MDM).

The proxy forwards requests to Bedrock Mantle, receives the responses, and emits a span for each round trip. It sees every request: the model, the token counts, the latency, the developer identity if the tool sends it.

## Pointing a tool at the proxy

Any OpenAI-compatible client can be pointed at the proxy by changing the base URL:

```python
from openai import OpenAI

client = OpenAI(
    api_key="not-used",
    base_url="http://localhost:8000/v1",
)
```

The `api_key` value is ignored by the proxy (authentication is handled separately at the Bedrock Mantle layer). The proxy intercepts the request, records telemetry, and forwards it upstream.

## Running it

```bash
cd ai-aws-bedrock-1

pip install -r dev-04-team-proxy/requirements.txt

export AWS_REGION=us-east-2
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

python dev-04-team-proxy/app-instrumented.py
```

The proxy listens on `localhost:8000` by default. Configure your AI tools to use `http://localhost:8000/v1` as the base URL.

## The plain proxy (before)

```python title="dev-04-team-proxy/app.py"
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aws_bedrock_token_generator import provide_token

BEDROCK_MANTLE_URL = "https://bedrock-mantle.us-east-2.api.aws/v1/chat/completions"

app = FastAPI()


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_name = body.get("model", "unknown")
    print(f"Request received: model={model_name}")

    async with httpx.AsyncClient() as http:
        upstream = await http.post(
            BEDROCK_MANTLE_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {provide_token()}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )

    return JSONResponse(content=upstream.json(), status_code=upstream.status_code)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

This forwards requests but records nothing.

## The instrumented proxy

```python title="dev-04-team-proxy/app-instrumented.py"
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aws_bedrock_token_generator import provide_token

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

# --- OTel setup ---
resource = Resource.create({"service.name": "ai-dev-proxy"})

provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

tracer = trace.get_tracer("ai-dev-proxy", "1.0.0")
meter  = metrics.get_meter("ai-dev-proxy", "1.0.0")

token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

BEDROCK_MANTLE_URL = "https://bedrock-mantle.us-east-2.api.aws/v1/chat/completions"

app = FastAPI()

print("AI proxy running on :8000. Point your tools at http://localhost:8000")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body         = await request.json()
    model_name   = body.get("model", "unknown")
    developer_id = request.headers.get("X-Developer-ID", "unknown")

    with tracer.start_as_current_span(f"chat {model_name}") as span:
        span.set_attribute("gen_ai.provider.name",  "anthropic")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model",  model_name)
        span.set_attribute("developer.id",          developer_id)

        async with httpx.AsyncClient() as http:
            upstream = await http.post(
                BEDROCK_MANTLE_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {provide_token()}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )

        response_body  = upstream.json()
        response_model = response_body.get("model", model_name)
        finish_reasons = [c["finish_reason"] for c in response_body.get("choices", [])]
        usage          = response_body.get("usage", {})
        input_tokens   = usage.get("prompt_tokens", 0)
        output_tokens  = usage.get("completion_tokens", 0)

        span.set_attribute("gen_ai.response.model",          response_model)
        span.set_attribute("gen_ai.response.finish_reasons", finish_reasons)
        span.set_attribute("gen_ai.usage.input_tokens",      input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens",     output_tokens)

        common_attrs = {
            "gen_ai.provider.name":  "anthropic",
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model":  model_name,
            "gen_ai.response.model": response_model,
        }
        token_usage.record(input_tokens,  {**common_attrs, "gen_ai.token.type": "input"})
        token_usage.record(output_tokens, {**common_attrs, "gen_ai.token.type": "output"})

        return JSONResponse(content=response_body, status_code=upstream.status_code)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Developer identity with X-Developer-ID

The proxy reads an `X-Developer-ID` header from each incoming request:

```python
developer_id = request.headers.get("X-Developer-ID", "unknown")
```

AI tools can add this header when they make requests. Claude Code, for example, can be configured to include custom headers. Scripts using the OpenAI client can set it directly:

```python
response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    extra_headers={"X-Developer-ID": "alice"},
)
```

Alternatively, if you run one proxy instance per developer (useful for local deployments), you can bake the identity into the proxy's environment rather than relying on the client to send it.

???+ question "Do I have to run this locally?"
    No. For team-wide deployment, run the proxy centrally (ECS, Lambda, Kubernetes) and push the endpoint configuration to developer machines via MDM or a simple shell profile.

    AWS makes this natural: run the proxy in the same account as your Bedrock Mantle access, and all developer traffic routes through one place. Each developer's tool is configured with the central proxy URL. The AWS credentials for Bedrock stay on the server, not on developer machines.

    Local deployment is useful during evaluation. Central deployment is better for ongoing team-wide observability.

## What you'll see in Dynatrace

After routing a few AI tool sessions through the proxy, open Dynatrace and look for the service `dev-ai-proxy`. You'll see:

- One span per AI call, across every developer who uses the proxy
- `gen_ai.request.model` showing the model breakdown across your team
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` per request
- `developer.id` so you can filter by individual developer
- The `gen_ai.client.token.usage` metric, aggregated across all calls

At this point you can answer questions that weren't answerable before: how many AI calls does your team make per day? Which models are most used? Is one session generating 10x the average token count?

That last question is where the "tragedy of the commons" becomes visible. When one developer's session accounts for a disproportionate share of tokens, that shows up immediately in the `developer.id` breakdown. You have a specific, factual starting point for a conversation, rather than a vague sense that costs are high.

Step 5 adds cost calculation on top of this, so you can translate token counts into dollars.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 5: Cost Attribution →](05-cost-attribution/)
