"""Developer AI assistant — code explanation, test generation, security review. With OTel observability."""

# Configure the collector via env vars:
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
#   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <token>

from openai import OpenAI
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
resource = Resource.create({"service.name": "dev-ai-assistant"})

provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

tracer = trace.get_tracer("dev-ai-assistant", "1.0.0")
meter  = metrics.get_meter("dev-ai-assistant", "1.0.0")

token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# --- client ---
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

MODEL = "anthropic.claude-3-5-haiku-20241022"

FUNCTION_UNDER_REVIEW = """
def process_batch(records, transform_fn, batch_size=100):
    results = []
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        transformed = [transform_fn(r) for r in batch]
        results.extend(transformed)
    return results
"""


def run_task(span_name: str, user_message: str) -> str:
    with tracer.start_as_current_span(span_name) as span:
        span.set_attribute("gen_ai.provider.name",  "anthropic")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model",  MODEL)

        messages = [{"role": "user", "content": user_message}]
        response = client.chat.completions.create(model=MODEL, messages=messages)

        span.set_attribute("gen_ai.response.model", response.model)
        span.set_attribute("gen_ai.response.finish_reasons",
                           [c.finish_reason for c in response.choices])

        if response.usage:
            span.set_attribute("gen_ai.usage.input_tokens",  response.usage.prompt_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)

            common_attrs = {
                "gen_ai.provider.name":  "anthropic",
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model":  MODEL,
                "gen_ai.response.model": response.model,
            }
            token_usage.record(response.usage.prompt_tokens,
                               {**common_attrs, "gen_ai.token.type": "input"})
            token_usage.record(response.usage.completion_tokens,
                               {**common_attrs, "gen_ai.token.type": "output"})

        return response.choices[0].message.content or ""


result = run_task(
    "chat explain-code",
    f"Explain what this Python function does:\n\n{FUNCTION_UNDER_REVIEW}",
)
print("=== Explanation ===")
print(result)

result = run_task(
    "chat generate-tests",
    f"Write pytest unit tests for this function:\n\n{FUNCTION_UNDER_REVIEW}",
)
print("\n=== Unit Tests ===")
print(result)

result = run_task(
    "chat security-review",
    f"Review this function for security issues:\n\n{FUNCTION_UNDER_REVIEW}",
)
print("\n=== Security Review ===")
print(result)

provider.shutdown()
meter_provider.shutdown()
