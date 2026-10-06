"""
Customer support response demo — model migration with OpenFeature + OpenTelemetry.

Each complaint is routed to either the control or challenger model based on a
flagd feature flag. Edit flags.json while flagd is running and the split
changes within seconds — no restart needed.

The trace structure for each complaint looks like this:

  triage {complaint_id}                       ← root span, covers full lifecycle
    feature_flag.key      = "active-model"
    feature_flag.variant  = "control" | "challenger"
    feature_flag.provider = "flagd"

    chat {model_name}                         ← LLM call
      gen_ai.request.model = ...
      gen_ai.usage.input_tokens = ...
      gen_ai.usage.output_tokens = ...

The metric gen_ai.model_selection.requests tracks how many complaints were
routed to each variant, so you can verify the split is working before
reading the quality results.

Usage: python app-instrumented.py [complaint_id]   (default: runs all)

Env vars:
  AWS_REGION                    e.g. us-east-2
  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://localhost:4318

Requires flagd running:
  flagd start --uri file:./flags.json

Install:
  pip install -r requirements.txt
"""

import json
import pathlib
import sys

from openai import OpenAI
from aws_bedrock_token_generator import provide_token
from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType

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
HERE = pathlib.Path(__file__).parent

MODEL_CONTROL    = "openai.gpt-oss-120b"
MODEL_CHALLENGER = "openai.gpt-oss-20b"

SYSTEM_PROMPT = """\
You are a senior customer support agent. Write a detailed, personalised response to the customer's complaint.

Address the customer by name. Be specific about what action is being taken and when.
Write in flowing prose, no bullet points or headers.\
"""

# ---------------------------------------------------------------------------
# OTel setup
# ---------------------------------------------------------------------------
resource = Resource.create({"service.name": "support-model-selection"})

_trace_provider = TracerProvider(resource=resource)
_trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(_trace_provider)

_meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(_meter_provider)

tracer = trace.get_tracer("support-model-selection", "1.0.0")
meter  = metrics.get_meter("support-model-selection", "1.0.0")

token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# Tracks how many requests were routed to each model variant.
# Use this to verify the feature flag split is working before reading
# quality results — if you set challenger to 10% and run 50 complaints,
# you should see roughly 5 in the challenger bucket.
model_requests = meter.create_counter(
    name="gen_ai.model_selection.requests",
    unit="{request}",
    description="Requests routed to each model variant",
)

# ---------------------------------------------------------------------------
# OpenFeature setup — reads flags.json directly on every evaluation.
# No server, no extra dependencies. Edit the file and the next request picks
# up the change immediately.
# ---------------------------------------------------------------------------
api.set_provider(FlagdProvider(
    resolver_type=ResolverType.FILE,
    offline_flag_source_path=str(HERE / "flags.json"),
))
flag_client = api.get_client()

# ---------------------------------------------------------------------------
# OpenAI client (Bedrock Mantle)
# ---------------------------------------------------------------------------
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)


# ---------------------------------------------------------------------------
# Urgency scoring — always uses the control model; result gates flag routing
# ---------------------------------------------------------------------------
def _get_urgency(message: str) -> int:
    system_prompt = (HERE.parent / "agentic-pipeline" / ".agents" / "sentiment.md").read_text()
    with tracer.start_as_current_span("invoke_agent sentiment") as agent_span:
        agent_span.set_attribute("gen_ai.operation.name", "invoke_agent")
        agent_span.set_attribute("gen_ai.agent.name",     "sentiment")
        agent_span.set_attribute("gen_ai.provider.name",  "aws.bedrock")

        with tracer.start_as_current_span(f"chat {MODEL_CONTROL}") as span:
            span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model",  MODEL_CONTROL)
            span.set_attribute("gen_ai.agent.name",     "sentiment")
            span.set_attribute("gen_ai.input.messages",
                               json.dumps([{"role": "user", "content": message}]))

            response = client.chat.completions.create(
                model=MODEL_CONTROL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": message},
                ],
            )
            raw = response.choices[0].message.content or ""
            span.set_attribute("gen_ai.response.model", response.model)
            span.set_attribute("gen_ai.output.messages",
                               json.dumps([{"role": "assistant", "content": raw}]))

            if response.usage:
                span.set_attribute("gen_ai.usage.input_tokens",  response.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
                attrs = {
                    "gen_ai.provider.name":  "aws.bedrock",
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model":  MODEL_CONTROL,
                    "gen_ai.response.model": response.model,
                    "gen_ai.agent.name":     "sentiment",
                }
                token_usage.record(response.usage.prompt_tokens,
                                   {**attrs, "gen_ai.token.type": "input"})
                token_usage.record(response.usage.completion_tokens,
                                   {**attrs, "gen_ai.token.type": "output"})

    try:
        return json.loads(raw).get("urgency", 3)
    except json.JSONDecodeError:
        return 3


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------
def triage(complaint: dict) -> None:
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")

    with tracer.start_as_current_span(f"triage {cid}") as root:
        root.set_attribute("complaint.id",       cid)
        root.set_attribute("complaint.customer", customer)

        # Score urgency first — high-urgency complaints always get the 120b model;
        # only low-urgency ones are eligible for the 20b challenger.
        urgency = _get_urgency(message)
        root.set_attribute("complaint.urgency", urgency)
        print(f"  Urgency: {urgency}/5")

        # Use the complaint ID as the targeting key so the same complaint always
        # routes to the same model variant — consistent assignment across runs.
        ctx     = EvaluationContext(targeting_key=cid, attributes={"urgency": urgency})
        details = flag_client.get_string_details("active-model", MODEL_CONTROL, ctx)
        model   = details.value
        variant = details.variant or "control"

        print(f"  Model variant: {variant} ({model})")

        # Record the flag evaluation on the root span so you can filter
        # all traces by variant directly at the top level in Dynatrace.
        root.set_attribute("feature_flag.key",      "active-model")
        root.set_attribute("feature_flag.variant",  variant)
        root.set_attribute("feature_flag.provider", "flagd")

        # Record the routing decision in the counter metric so you can verify
        # the split percentage before drawing conclusions from quality metrics.
        model_requests.add(1, {
            "feature_flag.key":     "active-model",
            "feature_flag.variant": variant,
            "gen_ai.request.model": model,
        })

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Customer name: {customer}\nComplaint: {message}"},
        ]

        with tracer.start_as_current_span(f"chat {model}") as span:
            span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model",  model)
            span.set_attribute("gen_ai.input.messages",
                               json.dumps([{"role": "user", "content": message}]))

            response = client.chat.completions.create(model=model, messages=messages)
            draft    = response.choices[0].message.content or ""

            span.set_attribute("gen_ai.response.model",          response.model)
            span.set_attribute("gen_ai.response.finish_reasons",
                               [c.finish_reason for c in response.choices])
            span.set_attribute("gen_ai.output.messages",
                               json.dumps([{
                                   "role":          "assistant",
                                   "content":       draft,
                                   "finish_reason": response.choices[0].finish_reason,
                               }]))

            if response.usage:
                span.set_attribute("gen_ai.usage.input_tokens",  response.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
                attrs = {
                    "gen_ai.provider.name":  "aws.bedrock",
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model":  model,
                    "gen_ai.response.model": response.model,
                    "feature_flag.variant":  variant,
                }
                token_usage.record(response.usage.prompt_tokens,
                                   {**attrs, "gen_ai.token.type": "input"})
                token_usage.record(response.usage.completion_tokens,
                                   {**attrs, "gen_ai.token.type": "output"})

        root.set_attribute("triage.outcome", "responded")
        print(f"\n  Draft response:\n\n  {draft.replace(chr(10), chr(10) + '  ')}")


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
    triage(complaint)

_trace_provider.shutdown()
_meter_provider.shutdown()
