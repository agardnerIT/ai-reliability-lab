"""
Customer support response demo — streaming output with OpenTelemetry.

Streaming changes the instrumentation pattern in three important ways:

  1. The span stays open for the full duration of the stream. Token counts,
     finish_reason, and response content cannot be set until the stream ends —
     they are deferred to after the iteration loop.

  2. Time-to-first-chunk must be measured with a wall-clock timer. We start
     the clock just before opening the stream and record the elapsed time when
     the first content-bearing chunk arrives. This is exposed as both a span
     attribute (gen_ai.response.time_to_first_chunk) and a histogram metric
     (gen_ai.client.operation.time_to_first_chunk, unit: s).

  3. Token usage arrives on the final (empty) chunk, not in a response.usage
     field, because there is no single response object. This requires
     stream_options={"include_usage": True} on the request.

Usage: python app-instrumented.py [complaint_id]   (default: runs all)

Env vars:
  AWS_REGION                    e.g. us-east-2
  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://localhost:4318
"""

import json
import pathlib
import sys
import time

from openai import OpenAI
from aws_bedrock_token_generator import provide_token

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HERE  = pathlib.Path(__file__).parent
MODEL = "openai.gpt-oss-120b"

SYSTEM_PROMPT = """\
You are a senior customer support agent writing a detailed, personalised response to a customer complaint.

Your response must include all of the following sections, in order:

1. Personal acknowledgement — address the customer by name, acknowledge exactly what went wrong, and apologise sincerely. Do not use generic phrases like "we are sorry for any inconvenience".
2. What we are doing right now — describe the specific remedy being applied (refund, replacement, escalation) and give a concrete timeline (e.g. "within 2 business days").
3. How to track it — tell the customer what they will receive (email confirmation, tracking number, callback) and when to expect it.
4. What to do if this is not resolved — give a direct escalation path: a named team, email address (support@example.com), or reference number they can quote.
5. Goodwill gesture — offer something concrete (discount code, priority shipping on next order) to acknowledge the inconvenience beyond just fixing the immediate problem.
6. Warm, personalised close — end on a human note that matches the tone of the complaint.

Write in a warm but professional tone. Use short paragraphs. Do not use bullet points or headers — write in flowing prose.\
"""

# ---------------------------------------------------------------------------
# OTel setup
# ---------------------------------------------------------------------------
resource = Resource.create({"service.name": "support-streaming"})

_trace_provider = TracerProvider(resource=resource)
_trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(_trace_provider)

_meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(_meter_provider)

tracer = trace.get_tracer("support-streaming", "1.0.0")
meter  = metrics.get_meter("support-streaming", "1.0.0")

# Token usage — same histogram as non-streaming examples.
token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# Time-to-first-chunk — streaming-specific metric per OTel GenAI semconv.
# Measures latency from request sent to first content byte received.
# Low p50 here means the model started generating quickly; a high p99 signals
# cold-start or scheduling delays on the provider side.
ttfc = meter.create_histogram(
    name="gen_ai.client.operation.time_to_first_chunk",
    unit="s",
    description="Time from request to first content chunk",
)

# ---------------------------------------------------------------------------
# OpenAI client — pointed at AWS Bedrock via the compatibility layer
# ---------------------------------------------------------------------------
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

# ---------------------------------------------------------------------------
# Stream a response for a single complaint
# ---------------------------------------------------------------------------
def respond(complaint: dict) -> None:
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")
    print(f"  \"{message}\"")
    print(f"\n  Streaming response:\n\n  ")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Customer name: {customer}\nComplaint: {message}"},
    ]

    with tracer.start_as_current_span(f"respond {cid}") as root:
        root.set_attribute("complaint.id",       cid)
        root.set_attribute("complaint.customer", customer)

        # The span opens before the stream does and closes after iteration ends.
        # This means the span duration == total time to stream the full response,
        # which is the correct end-to-end latency for a streaming inference call.
        with tracer.start_as_current_span(f"chat {MODEL}") as span:
            span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model",  MODEL)
            span.set_attribute("gen_ai.request.stream", True)
            span.set_attribute("gen_ai.input.messages",
                               json.dumps([{"role": "user", "content": message}]))

            # Start the clock immediately before opening the stream so we capture
            # any connection/scheduling overhead in the time-to-first-chunk measurement.
            start = time.perf_counter()
            first_chunk_elapsed: float | None = None

            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                stream=True,
                # include_usage=True causes the provider to emit a final chunk
                # containing token counts. Without this, usage is unavailable in
                # streaming mode and gen_ai.usage.* cannot be set on the span.
                stream_options={"include_usage": True},
            )

            content_chunks: list[str] = []
            finish_reason: str | None = None

            for chunk in stream:
                # Content chunks — accumulate for the final gen_ai.output.messages attribute
                # and record time-to-first-chunk on the first one.
                if chunk.choices and chunk.choices[0].delta.content:
                    if first_chunk_elapsed is None:
                        first_chunk_elapsed = time.perf_counter() - start
                    delta = chunk.choices[0].delta.content
                    content_chunks.append(delta)
                    print(delta, end="", flush=True)

                # finish_reason arrives on the last content chunk (choices[0].finish_reason
                # is None on all prior chunks).
                if chunk.choices and chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

                # Token usage arrives on a final empty chunk (no choices) when
                # stream_options={"include_usage": True} is set.
                if chunk.usage:
                    span.set_attribute("gen_ai.usage.input_tokens",  chunk.usage.prompt_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", chunk.usage.completion_tokens)
                    metric_attrs = {
                        "gen_ai.provider.name":  "aws.bedrock",
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model":  MODEL,
                    }
                    token_usage.record(chunk.usage.prompt_tokens,
                                       {**metric_attrs, "gen_ai.token.type": "input"})
                    token_usage.record(chunk.usage.completion_tokens,
                                       {**metric_attrs, "gen_ai.token.type": "output"})

            # --- Deferred span attributes — set after the stream is fully consumed ---

            # gen_ai.response.time_to_first_chunk: how long before content started arriving.
            # Only set if at least one content chunk was received.
            if first_chunk_elapsed is not None:
                span.set_attribute("gen_ai.response.time_to_first_chunk", first_chunk_elapsed)
                ttfc.record(first_chunk_elapsed, {
                    "gen_ai.provider.name":  "aws.bedrock",
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model":  MODEL,
                })

            span.set_attribute("gen_ai.response.finish_reasons",
                               [finish_reason] if finish_reason else [])
            span.set_attribute("gen_ai.output.messages",
                               json.dumps([{
                                   "role":         "assistant",
                                   "content":      "".join(content_chunks),
                                   "finish_reason": finish_reason,
                               }]))

    print("\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
complaints = json.loads((HERE / "complaints.json").read_text())

if len(sys.argv) > 1:
    target_id = sys.argv[1].upper()
    complaints = [c for c in complaints if c["id"] == target_id]
    if not complaints:
        print(f"Complaint {target_id} not found.")
        sys.exit(1)

for complaint in complaints:
    respond(complaint)

_trace_provider.shutdown()
_meter_provider.shutdown()
