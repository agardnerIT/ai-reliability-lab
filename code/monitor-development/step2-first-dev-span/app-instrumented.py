# AI-powered code reviewer with OTel instrumentation.
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
resource = Resource.create({"service.name": "code-reviewer"})

provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

tracer = trace.get_tracer("code-reviewer", "1.0.0")
meter  = metrics.get_meter("code-reviewer", "1.0.0")

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

STACK_CLASS = """
class Stack:
    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        if self.is_empty():
            raise IndexError("pop from empty stack")
        return self._items.pop()

    def peek(self):
        if self.is_empty():
            raise IndexError("peek at empty stack")
        return self._items[-1]

    def is_empty(self):
        return len(self._items) == 0

    def size(self):
        return len(self._items)
"""

messages = [
    {
        "role": "user",
        "content": f"Review this Python class for correctness, style, and potential improvements:\n\n{STACK_CLASS}",
    }
]

with tracer.start_as_current_span("chat code-review") as span:
    span.set_attribute("gen_ai.provider.name",  "anthropic")
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.request.model",  MODEL)
    # Custom attribute to tag dev context — useful for filtering spans by task type
    span.set_attribute("developer.task", "code-review")

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

    print(response.choices[0].message.content)

provider.shutdown()
meter_provider.shutdown()
