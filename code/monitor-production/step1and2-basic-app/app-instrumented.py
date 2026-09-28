# Save as test.py and run: python test.py
# Requires: opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
# Configure the collector via env vars:
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
#   OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer <token>

import json

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
# Both exporters read OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS
resource = Resource.create({"service.name": "bedrock-chat-client"})

provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

tracer = trace.get_tracer("bedrock-chat-client", "1.0.0")
meter = metrics.get_meter("bedrock-chat-client", "1.0.0")

# GenAI semconv metric: gen_ai.client.token.usage (histogram, unit: {token})
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

MODEL = "openai.gpt-oss-120b"
MESSAGES = [{"role": "user", "content": "What is Amazon Bedrock?"}]

operation = "chat"
span_name = f"{operation} {MODEL}"

with tracer.start_as_current_span(span_name) as span:
    span.set_attribute("gen_ai.provider.name", "aws.bedrock")
    span.set_attribute("gen_ai.operation.name", operation)
    span.set_attribute("gen_ai.request.model", MODEL)

    # gen_ai.input.messages is an opt-in span attribute per OTel GenAI semconv.
    # Recorded as a JSON string (structured form) per spec §gen-ai-spans.
    span.set_attribute("gen_ai.input.messages",
                       json.dumps([{"role": m["role"], "content": m["content"]} for m in MESSAGES]))

    response = client.chat.completions.create(model=MODEL, messages=MESSAGES)

    # Response attributes
    span.set_attribute("gen_ai.response.model", response.model)
    span.set_attribute("gen_ai.response.finish_reasons", [c.finish_reason for c in response.choices])
    if response.usage:
        span.set_attribute("gen_ai.usage.input_tokens", response.usage.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)

        common_attrs = {
            "gen_ai.provider.name":  "aws.bedrock",
            "gen_ai.operation.name": operation,
            "gen_ai.request.model":  MODEL,
            "gen_ai.response.model": response.model,
        }
        token_usage.record(response.usage.prompt_tokens,     {**common_attrs, "gen_ai.token.type": "input"})
        token_usage.record(response.usage.completion_tokens, {**common_attrs, "gen_ai.token.type": "output"})

    # gen_ai.output.messages is an opt-in span attribute per OTel GenAI semconv.
    span.set_attribute("gen_ai.output.messages",
                       json.dumps([{
                           "role":         c.message.role,
                           "content":      c.message.content or "",
                           "finish_reason": c.finish_reason,
                       } for c in response.choices]))

    print(response.choices[0].message.content)

    # Debug: full response structure
    print("\n--- DEBUG: raw response ---")
    print(response)
    print("\n--- DEBUG: usage fields ---")
    print(f"usage object: {response.usage}")
    if response.usage:
        print(f"  prompt_tokens:     {response.usage.prompt_tokens}")
        print(f"  completion_tokens: {response.usage.completion_tokens}")
        print(f"  total_tokens:      {response.usage.total_tokens}")
        print(f"  all usage attrs:   {vars(response.usage)}")

provider.shutdown()
meter_provider.shutdown()
