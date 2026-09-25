# Step 5: Cost Attribution

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
    <a href="../04-team-proxy/" class="dt-trail-step inactive">Step 4: Enterprise Push</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 5: AI Gateway</span>
  </div>
</div>

Token counts tell you what happened. Cost figures are what prompt action.

This step adds a `PRICING` table to the proxy and emits a `gen_ai.client.cost.usd` metric per request, tagged with the developer's identity. The proxy from Step 4 stays unchanged except for these additions.

## The pricing table

```python title="dev-05-cost-attribution/app-instrumented.py (excerpt)"
# USD per 1M tokens
PRICING = {
    "anthropic.claude-3-5-haiku-20241022":  {"input": 0.80,  "output": 4.00},
    "anthropic.claude-3-5-sonnet-20241022": {"input": 3.00,  "output": 15.00},
    "anthropic.claude-sonnet-4-5":          {"input": 3.00,  "output": 15.00},
    "anthropic.claude-opus-4-5":            {"input": 15.00, "output": 75.00},
    "openai.gpt-oss-120b":                  {"input": 2.50,  "output": 10.00},
}
```

Model pricing changes. Treat this table as configuration you maintain rather than a static constant. If your team uses models not in this table, requests for those models will record zero cost, which is misleading. Better to log a warning when an unknown model is encountered so you can update the table.

## The full instrumented proxy

```python title="dev-05-cost-attribution/app-instrumented.py"
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

# USD per 1M tokens
PRICING = {
    "anthropic.claude-3-5-haiku-20241022":  {"input": 0.80,  "output": 4.00},
    "anthropic.claude-3-5-sonnet-20241022": {"input": 3.00,  "output": 15.00},
    "anthropic.claude-sonnet-4-5":          {"input": 3.00,  "output": 15.00},
    "anthropic.claude-opus-4-5":            {"input": 15.00, "output": 75.00},
    "openai.gpt-oss-120b":                  {"input": 2.50,  "output": 10.00},
}

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

# Histogram rather than gauge: lets you aggregate cost across requests
# and compute percentiles; gauge would only show the last value per scrape.
cost_usd = meter.create_histogram(
    name="gen_ai.client.cost.usd",
    unit="USD",
    description="Estimated cost of a GenAI request in US dollars",
)

BEDROCK_MANTLE_URL = "https://bedrock-mantle.us-east-2.api.aws/v1/chat/completions"

app = FastAPI()

print("AI proxy running on :8000. Point your tools at http://localhost:8000")


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> tuple[float, float]:
    rates = PRICING.get(model)
    if not rates:
        return 0.0, 0.0
    input_cost  = (input_tokens  / 1_000_000) * rates["input"]
    output_cost = (output_tokens / 1_000_000) * rates["output"]
    return input_cost, output_cost


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
            "developer.id":          developer_id,
        }
        token_usage.record(input_tokens,  {**common_attrs, "gen_ai.token.type": "input"})
        token_usage.record(output_tokens, {**common_attrs, "gen_ai.token.type": "output"})

        input_cost, output_cost = _calculate_cost(model_name, input_tokens, output_tokens)
        cost_attrs = {
            "developer.id":         developer_id,
            "gen_ai.request.model": model_name,
        }
        cost_usd.record(input_cost,  {**cost_attrs, "gen_ai.token.type": "input"})
        cost_usd.record(output_cost, {**cost_attrs, "gen_ai.token.type": "output"})

        return JSONResponse(content=response_body, status_code=upstream.status_code)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## What changed from Step 4

Two additions on top of the Step 4 proxy:

**The cost metric:**

```python
cost_metric = meter.create_histogram(
    name="gen_ai.client.cost.usd",
    unit="USD",
    description="Estimated cost of a GenAI request in USD",
)
```

**Recording it per request, with developer identity attached:**

```python
estimated_cost = calculate_cost(response_model, input_tokens, output_tokens)
span.set_attribute("gen_ai.client.cost.usd", estimated_cost)
cost_metric.record(estimated_cost, common_attrs)
```

The `developer.id` dimension is already in `common_attrs` from Step 4. Attaching it to the cost metric means you can aggregate total cost per developer over any time period.

## From token counts to targeted action

Token counts tell you what happened. Cost attribution tells you what it means financially, and who is responsible for which portion of it.

The key shift is from reactive to specific. Without this data, an organisation that gets a surprise AI spend invoice has one blunt option: restrict access. With this data, the same organisation can look at the `gen_ai.client.cost.usd` metric, filter by `developer.id`, and see immediately whether one person's workflow accounts for 40% of the bill.

Instead of capping everyone, you can reach out to one person, understand what they're doing, and find a better approach. Everyone else keeps working normally.

## Setting alerts in Dynatrace

Dynatrace can alert on metrics. With `gen_ai.client.cost.usd` flowing in, you can set a metric alert that fires when any individual developer's rolling cost exceeds a threshold. The alert can notify the developer directly (via email, Slack, or PagerDuty) rather than going to a manager.

That framing matters. A developer who gets a heads-up that their AI spend is trending high can adjust their workflow. A developer who finds out through a blanket policy change has no idea what they did or how to change it.

## What you'll see in Dynatrace

Open the `gen_ai.client.cost.usd` metric in Dynatrace Metrics and split by `developer.id`. You'll see a cost breakdown showing each developer's contribution to total AI spend.

Split the same metric by `gen_ai.response.model` to see which models are driving the most cost. Often the answer is surprising: a cheaper model handles 80% of the volume, but an expensive one accounts for 80% of the spend because of a few high-token sessions.

The dashboard you can build from this data gives your organisation a factual basis for the AI spend conversation, one that enables precise decisions rather than blunt ones.

## A note on what to do with this data

What you do with cost attribution data is an organisational decision. Some teams use it as an informational dashboard only, reviewed in monthly retrospectives. Others set per-developer soft budgets with automated alerts. Both approaches are valid uses of this data.

The goal of the telemetry is visibility, not control. Visibility lets organisations make informed decisions. What those decisions are is up to the people making them.

<div id="dt-quiz-anchor"></div>

## You've completed the path

You started with a script that made AI calls in the dark. You now have:

- A pattern for instrumenting scripts you control ([Step 2](02-first-dev-span/))
- A hook for harnesses you don't control ([Step 3](../03-claude-code-hook/))
- A proxy that sees all developer AI traffic in one place ([Step 4](04-team-proxy/))
- Per-developer cost attribution ([Step 5](05-cost-attribution/))

The [Monitor Production AI](../monitor-production/index.md) path covers the same observability concepts for AI features running in production.
