"""
Customer support escalation demo.
Usage: python demo.py [complaint_id]   (default: runs all complaints)

Env vars required:
  AWS_REGION                      e.g. us-east-2
  OTEL_EXPORTER_OTLP_ENDPOINT     e.g. http://localhost:4318
"""

import json
import pathlib
import sys

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
# Absolute path so agent files resolve correctly regardless of working directory
HERE = pathlib.Path(__file__).parent
MODEL = "openai.gpt-oss-120b"
ESCALATION_THRESHOLD = 4  # urgency >= this → hand off to human

# ---------------------------------------------------------------------------
# OTel setup
# ---------------------------------------------------------------------------
resource = Resource.create({"service.name": "support-triage-pipeline"})

_trace_provider = TracerProvider(resource=resource)
_trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(_trace_provider)

_meter_provider = MeterProvider(
    resource=resource,
    # Export interval doesn't matter here — shutdown() forces a flush before exit
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(_meter_provider)

tracer = trace.get_tracer("support-triage-agent", "1.0.0")
meter  = metrics.get_meter("support-triage-agent", "1.0.0")

# gen_ai.client.token.usage is the GenAI semconv histogram for token cost tracking
token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)


def _load_agent(name: str) -> str:
    return (HERE / ".agents" / f"{name}.md").read_text()


def _call_agent(agent_name: str, user_message: str) -> str:
    system_prompt = _load_agent(agent_name)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    # Outer span represents invoking a named sub-agent (OTel GenAI semconv: invoke_agent).
    # Inner span represents the actual LLM inference call (OTel GenAI semconv: chat).
    with tracer.start_as_current_span(f"invoke_agent {agent_name}") as agent_span:
        agent_span.set_attribute("gen_ai.operation.name", "invoke_agent")
        agent_span.set_attribute("gen_ai.agent.name",     agent_name)
        agent_span.set_attribute("gen_ai.provider.name",  "aws.bedrock")

        with tracer.start_as_current_span(f"chat {MODEL}") as span:
            span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model",  MODEL)
            span.set_attribute("gen_ai.agent.name",     agent_name)
            # gen_ai.input.messages / gen_ai.output.messages are opt-in span
            # attributes per OTel GenAI semconv §gen-ai-spans.
            span.set_attribute("gen_ai.input.messages",
                               json.dumps([{"role": "user", "content": user_message}]))

            response = client.chat.completions.create(model=MODEL, messages=messages)

            content = response.choices[0].message.content or ""
            span.set_attribute("gen_ai.response.model", response.model)
            span.set_attribute("gen_ai.response.finish_reasons",
                               [c.finish_reason for c in response.choices])
            span.set_attribute("gen_ai.output.messages",
                               json.dumps([{
                                   "role":         "assistant",
                                   "content":      content,
                                   "finish_reason": response.choices[0].finish_reason,
                               }]))

            if response.usage:
                span.set_attribute("gen_ai.usage.input_tokens",  response.usage.prompt_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
                attrs = {
                    "gen_ai.provider.name":  "aws.bedrock",
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model":  MODEL,
                    "gen_ai.response.model": response.model,
                    "gen_ai.agent.name":     agent_name,
                }
                token_usage.record(response.usage.prompt_tokens,
                                   {**attrs, "gen_ai.token.type": "input"})
                token_usage.record(response.usage.completion_tokens,
                                   {**attrs, "gen_ai.token.type": "output"})

    return content


# ---------------------------------------------------------------------------
# Triage pipeline
# ---------------------------------------------------------------------------
def triage(complaint: dict) -> None:
    # This is the main pipeline. It always runs the same three agents in the same order.
    # The routing logic (whether to escalate or respond) lives here in code, not in the LLM.
    # Contrast with agentic-loop/demo.py where the LLM decides what to call and when.
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]
    policy   = (HERE / "policy.md").read_text()

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")
    print(f"  \"{message}\"")

    # The root span covers the entire triage operation for this complaint.
    # All agent spans created inside _call_agent() will be children of this span,
    # giving us a single trace per complaint in Dynatrace.
    with tracer.start_as_current_span(f"triage {cid}") as root:
        root.set_attribute("complaint.id",       cid)
        root.set_attribute("complaint.customer", customer)

        # --- Agent 1: sentiment ---
        # Always runs first. Every complaint goes through sentiment scoring regardless
        # of content, because we need the urgency score before we can make any routing decision.
        # The sentiment agent returns JSON with urgency (1-5), sentiment label, and reasoning.
        # see .agents/sentiment.md
        raw = _call_agent("sentiment", message)
        try:
            assessment = json.loads(raw)
        except json.JSONDecodeError:
            # LLMs don't always honour JSON-only instructions; default to mid-range urgency
            assessment = {"urgency": 3, "sentiment": "unknown", "reasoning": raw}

        urgency = assessment.get("urgency", 3)
        # Urgency and sentiment are set on the root span so they're visible at the trace level
        # without needing to inspect the child sentiment span.
        root.set_attribute("complaint.urgency",   urgency)
        root.set_attribute("complaint.sentiment", assessment.get("sentiment", ""))
        print(f"\n  Urgency: {urgency}/5 — {assessment.get('sentiment')} — {assessment.get('reasoning')}")

        # --- Escalation gate ---
        # This is the only branching point in the pipeline. If urgency is high (legal threats,
        # bank disputes, repeated failures), we stop here and hand off to a human.
        # No policy check or draft is attempted — escalated complaints need human judgement,
        # not an automated response. triage.outcome on the root span records which path was taken.
        if urgency >= ESCALATION_THRESHOLD:
            root.set_attribute("triage.outcome", "escalated")
            print(f"\n  *** ESCALATED TO HUMAN AGENT ***")
            return

        # --- Agent 2: policy checker ---
        # Only reached if urgency is below the escalation threshold.
        # The full policy.md is passed alongside the complaint so the agent can match
        # the specific situation (damaged item, wrong item, late delivery, etc.) to the
        # correct remedy without hardcoding any policy logic here in the orchestrator.
        # see .agents/policy_checker.md and policy.md
        policy_input = (
            f"Complaint: {message}\n\n"
            f"Policy:\n{policy}"
        )
        raw = _call_agent("policy_checker", policy_input)
        try:
            policy_result = json.loads(raw)
        except json.JSONDecodeError:
            policy_result = {"remedies": [raw], "notes": ""}

        remedies = policy_result.get("remedies", [])
        print(f"\n  Remedies: {', '.join(remedies)}")

        # --- Agent 3: draft response ---
        # Only reached after a successful policy check. The draft agent is intentionally
        # kept separate from policy — it knows how to write, not what to offer. Passing
        # the approved remedies explicitly prevents it from inventing compensation that
        # isn't in policy.
        # see .agents/draft_response.md
        draft_input = (
            f"Customer name: {customer}\n"
            f"Complaint: {message}\n"
            f"Approved remedies: {', '.join(remedies)}\n"
            f"Notes: {policy_result.get('notes', '')}"
        )
        draft = _call_agent("draft_response", draft_input)

        root.set_attribute("triage.outcome", "responded")
        print(f"\n  Draft response:\n")
        print(f"  {draft.replace(chr(10), chr(10) + '  ')}")


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

# shutdown() forces BatchSpanProcessor and metric reader to flush before the process exits
_trace_provider.shutdown()
_meter_provider.shutdown()
