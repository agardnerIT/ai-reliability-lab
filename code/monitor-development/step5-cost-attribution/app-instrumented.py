# Team AI proxy with per-developer cost attribution.
# Calculates estimated USD cost per request and emits it as a metric,
# tagged with developer identity and model name.
#
# Run with: uvicorn app_instrumented:app --port 8000
#
# Configure the collector via env vars:
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
#   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <token>

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

# Histogram rather than gauge — histogram lets you aggregate cost across requests
# and compute percentiles; gauge would only show the last value per scrape.
cost_usd = meter.create_histogram(
    name="gen_ai.client.cost.usd",
    unit="USD",
    description="Estimated cost of a GenAI request in US dollars",
)

BEDROCK_MANTLE_URL = "https://bedrock-mantle.us-east-2.api.aws/v1/chat/completions"

app = FastAPI()

print("AI proxy running on :8000 — point your tools at http://localhost:8000")


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> tuple[float, float]:
    """Return (input_cost_usd, output_cost_usd) for the given model and token counts."""
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
        span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
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

        response_body = upstream.json()

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
            "gen_ai.provider.name":  "aws.bedrock",
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
