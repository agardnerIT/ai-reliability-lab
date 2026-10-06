"""
Customer support escalation demo — true agentic loop, with OpenTelemetry.

Architecture overview
---------------------
There are two distinct LLM roles here:

  1. Orchestrator  — the model inside triage(). It receives the complaint and
                     decides WHICH tools to call, in what order, and when to
                     stop. It never writes a customer-facing response itself.

  2. Sub-agents    — separate single-turn LLM calls (assess_sentiment,
                     check_policy, draft_response). Each has its own system
                     prompt loaded from .agents/<name>.md and knows nothing
                     about the orchestration loop around it.

The agentic loop works by repeatedly sending the growing message history back
to the orchestrator. The model's tool calls drive what happens next; the code
only dispatches what the model requests.

Observability structure
-----------------------
Every complaint produces a trace that looks like this:

  triage {complaint_id}                     ← root span, one per complaint
    chat openai.gpt-oss-120b  (turn 1)      ← orchestrator deciding what to call
      tool assess_sentiment                  ← tool span wraps the dispatch
        chat openai.gpt-oss-120b            ← sub-agent LLM call
      tool check_policy
        chat openai.gpt-oss-120b
      tool draft_response
        chat openai.gpt-oss-120b
    chat openai.gpt-oss-120b  (turn 2)      ← orchestrator producing final response

Attributes follow the OpenTelemetry GenAI semantic conventions (gen_ai.*).
Token counts are also recorded as a histogram metric so they can be
aggregated across complaints, agents, and time.

Usage: python app-instrumented.py [complaint_id]   (default: runs all)

Env vars:
  AWS_REGION                    e.g. us-east-2
  OTEL_EXPORTER_OTLP_ENDPOINT   e.g. http://localhost:4318
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
HERE  = pathlib.Path(__file__).parent
MODEL = "openai.gpt-oss-120b"

# The orchestrator prompt deliberately restricts the model to routing only.
# Without this constraint the model tends to answer the customer directly,
# short-circuiting the tool pipeline and skipping policy/sentiment checks.
ORCHESTRATOR_PROMPT = """\
You are a customer support routing agent. Your only job is to decide which tools to call and in what order — you do not assess, judge, write, or take any action yourself.

You have tools available to assess sentiment, check policy, draft a response, and escalate. Use your judgement about which are necessary and in what order given the complaint. You are not required to call all of them.

Do not write any response to the customer yourself. Do not summarise or interpret tool results. Only route.\
"""

# ---------------------------------------------------------------------------
# OTel setup
#
# A single Resource tags every span and metric point with the service name
# so they can be filtered in the backend. The same resource is shared between
# the tracer and meter providers so traces and metrics stay correlated.
#
# BatchSpanProcessor buffers spans and exports them in the background —
# lower overhead than the synchronous SimpleSpanProcessor.
#
# PeriodicExportingMetricReader pushes metrics on a fixed interval (default
# 60 s). Both exporters send to the OTLP HTTP endpoint configured via the
# OTEL_EXPORTER_OTLP_ENDPOINT env var.
# ---------------------------------------------------------------------------
resource = Resource.create({"service.name": "support-triage-loop"})

_trace_provider = TracerProvider(resource=resource)
_trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(_trace_provider)

_meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(_meter_provider)

# The tracer and meter are module-level singletons — one per file is standard.
# The version string ("1.0.0") appears in the instrumentation scope metadata.
tracer = trace.get_tracer("support-triage-loop", "1.0.0")
meter  = metrics.get_meter("support-triage-loop", "1.0.0")

# Histogram (not counter) because we want percentile distributions of token
# usage, not just totals. The name and unit follow the OpenTelemetry GenAI
# semantic conventions so backends (Dynatrace, Grafana, etc.) can auto-detect
# and visualise them without custom configuration.
token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# ---------------------------------------------------------------------------
# OpenAI client — pointed at AWS Bedrock via the compatibility layer
# ---------------------------------------------------------------------------
client = OpenAI(
    api_key=provide_token(),          # short-lived SigV4 token, not an OpenAI key
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

# ---------------------------------------------------------------------------
# Tool definitions — the LLM chooses from these
#
# Each entry is an OpenAI function-calling schema. The model reads the
# "description" fields to decide when to call each tool and which arguments
# to populate. The code never calls these directly — the model requests them
# and _dispatch() executes them.
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "assess_sentiment",
            "description": "Assess the urgency and sentiment of the complaint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "complaint": {"type": "string"},
                },
                "required": ["complaint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_policy",
            "description": "Check what remedies company policy allows for this complaint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "complaint": {"type": "string"},
                    # Optional — orchestrator passes sentiment output here when available
                    "context":   {"type": "string", "description": "Sentiment assessment result"},
                },
                "required": ["complaint"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_response",
            "description": "Draft a response to send to the customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string"},
                    "complaint":     {"type": "string"},
                    "remedies":      {"type": "string", "description": "Approved remedies from policy check"},
                },
                "required": ["customer_name", "complaint", "remedies"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            # The description teaches the model WHEN escalation is appropriate.
            # This is the only tool that terminates the loop without a drafted response.
            "description": "Escalate to a human senior agent. Use when the complaint involves legal threats, bank disputes, or repeated failures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Agent caller — invokes a sub-agent for a single task
#
# Each sub-agent is a stateless single-turn call: it gets a system prompt
# (its specialisation) and one user message (the task), then returns its
# output as a plain string. There is no shared memory between sub-agents;
# the orchestrator is responsible for passing relevant context between them
# via the tool arguments it constructs.
#
# The span created here becomes a child of whichever tool span called us,
# which in turn is a child of the orchestrator's turn span. This gives the
# trace its nested triage → tool → chat hierarchy.
# ---------------------------------------------------------------------------
def _load_agent(name: str) -> str:
    # System prompts live in .agents/<name>.md so they can be edited without
    # touching Python code.
    return (HERE / ".agents" / f"{name}.md").read_text()


def _call_agent(agent_name: str, user_message: str) -> str:
    system_prompt = _load_agent(agent_name)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    # Outer span: invoke_agent represents calling a named sub-agent (OTel GenAI semconv).
    # Inner span: chat {MODEL} represents the actual LLM inference call inside it.
    # This nesting makes the trace waterfall show agent invocation latency separately
    # from raw inference latency.
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
            # attributes per OTel GenAI semconv §gen-ai-spans. Recorded as JSON.
            span.set_attribute("gen_ai.input.messages",
                               json.dumps([{"role": "user", "content": user_message}]))

            response = client.chat.completions.create(model=MODEL, messages=messages)
            content  = response.choices[0].message.content or ""

            span.set_attribute("gen_ai.response.model",          response.model)
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
                # The same token counts go into the histogram metric with labels so
                # you can filter/aggregate by agent, model, or token type in dashboards.
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
# Tool dispatcher — bridges model tool-call names to actual sub-agent calls
#
# _dispatch() is the boundary between the orchestrator's decision (a tool
# name + JSON arguments) and the implementation (a sub-agent LLM call or
# direct logic). The "escalate" tool is the only one that does NOT invoke
# an LLM — it simply returns a structured JSON result so the loop can detect
# it and halt.
#
# The tool span wraps the full dispatch including any sub-agent call, so its
# duration reflects end-to-end latency for that tool step. tool.result_length
# gives a cheap proxy for how much context each tool adds to the conversation.
# ---------------------------------------------------------------------------
def _dispatch(tool_name: str, args: dict) -> str:
    # Policy is loaded fresh each call so changes take effect without restart.
    policy = (HERE / "policy.md").read_text()

    # Span name and operation follow OTel GenAI semconv: execute_tool {tool_name}.
    with tracer.start_as_current_span(f"execute_tool {tool_name}") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("tool.name", tool_name)

        if tool_name == "assess_sentiment":
            result = _call_agent("sentiment", args["complaint"])

        elif tool_name == "check_policy":
            # Combine complaint + full policy text into a single user message for
            # the policy-checker sub-agent. Sentiment context is optional.
            msg = f"Complaint: {args['complaint']}\n\nPolicy:\n{policy}"
            if "context" in args:
                msg += f"\n\nSentiment context: {args['context']}"
            result = _call_agent("policy_checker", msg)

        elif tool_name == "draft_response":
            msg = (
                f"Customer name: {args['customer_name']}\n"
                f"Complaint: {args['complaint']}\n"
                f"Approved remedies: {args['remedies']}"
            )
            result = _call_agent("draft_response", msg)

        elif tool_name == "escalate":
            # No LLM needed — just echo back a structured result. The loop checks
            # for this tool name specifically to decide whether to halt.
            result = json.dumps({"escalated": True, "reason": args["reason"]})

        else:
            result = json.dumps({"error": f"Unknown tool: {tool_name}"})

        span.set_attribute("tool.result_length", len(result))

    return result


# ---------------------------------------------------------------------------
# Agentic loop — the core of the demo
#
# Each iteration ("turn") sends the full conversation history to the
# orchestrator and asks it what to do next. The model either:
#   a) Returns tool_calls  → we dispatch each one, append results, loop again
#   b) Returns finish_reason=="stop" → the model is done; print final response
#   c) Calls "escalate"    → we halt immediately after the dispatch batch
#
# The growing `messages` list is the model's only memory across turns.
# Every assistant message and every tool result must be appended so the model
# can see the full history when deciding its next action.
#
# The root span "triage {cid}" covers the entire complaint lifecycle.
# triage.outcome and triage.turns are set just before the loop exits so the
# span always records how the complaint resolved.
# ---------------------------------------------------------------------------
def triage(complaint: dict) -> None:
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")
    print(f"  \"{message}\"")

    # Seed the conversation with the orchestrator system prompt and the complaint.
    messages = [
        {"role": "system", "content": ORCHESTRATOR_PROMPT},
        {"role": "user",   "content": f"Customer name: {customer}\nComplaint: {message}"},
    ]

    with tracer.start_as_current_span(f"triage {cid}") as root:
        root.set_attribute("complaint.id",       cid)
        root.set_attribute("complaint.customer", customer)

        turn = 0
        while True:
            turn += 1

            # Each orchestrator call gets its own child span so you can see
            # per-turn latency and token costs in the trace waterfall.
            # loop.turn lets you filter spans by iteration number.
            with tracer.start_as_current_span(f"chat {MODEL}") as span:
                span.set_attribute("gen_ai.provider.name",  "aws.bedrock")
                span.set_attribute("gen_ai.operation.name", "chat")
                span.set_attribute("gen_ai.request.model",  MODEL)
                span.set_attribute("loop.turn",             turn)

                # tool_choice="auto" lets the model decide whether to call a tool
                # or produce a final text response. We never force a specific tool.
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                choice = response.choices[0]

                span.set_attribute("gen_ai.response.model",          response.model)
                span.set_attribute("gen_ai.response.finish_reasons", [choice.finish_reason])
                if response.usage:
                    span.set_attribute("gen_ai.usage.input_tokens",  response.usage.prompt_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
                    # gen_ai.agent.name="orchestrator" distinguishes these metric
                    # points from sub-agent calls in the same histogram.
                    attrs = {
                        "gen_ai.provider.name":  "aws.bedrock",
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model":  MODEL,
                        "gen_ai.response.model": response.model,
                        "gen_ai.agent.name":     "orchestrator",
                    }
                    token_usage.record(response.usage.prompt_tokens,
                                       {**attrs, "gen_ai.token.type": "input"})
                    token_usage.record(response.usage.completion_tokens,
                                       {**attrs, "gen_ai.token.type": "output"})

            # Always append the assistant's turn to the history before dispatching.
            # The API requires the assistant message to appear in history before
            # the corresponding tool results, even if content is None (which happens
            # when the model returns tool_calls instead of a text response).
            assistant_msg = {"role": "assistant", "content": choice.message.content}
            if choice.message.tool_calls:
                # model_dump() converts the Pydantic ToolCall object to a plain dict,
                # which is the format required when re-sending it in the next request.
                assistant_msg["tool_calls"] = [
                    tc.model_dump() for tc in choice.message.tool_calls
                ]
            messages.append(assistant_msg)

            # finish_reason=="stop" means the model produced a final text response
            # with no further tool calls — the loop is complete.
            if choice.finish_reason == "stop":
                root.set_attribute("triage.outcome", "responded")
                root.set_attribute("triage.turns",   turn)
                print(f"\n  Draft response:\n")
                print(f"  {(choice.message.content or '').replace(chr(10), chr(10) + '  ')}")
                break

            # The model may request multiple tool calls in a single turn (parallel
            # tool use). We dispatch all of them before looping back.
            escalated = False
            for tc in (choice.message.tool_calls or []):
                tool_name = tc.function.name
                args      = json.loads(tc.function.arguments)
                print(f"\n  → {tool_name}({', '.join(f'{k}={repr(v)[:60]}' for k, v in args.items())})")

                result = _dispatch(tool_name, args)

                # Each tool result must be tied back to its originating tool call
                # via tool_call_id so the model can correlate them.
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

                if tool_name == "escalate":
                    # Don't break immediately — finish appending all tool results
                    # from this batch so the message history stays consistent.
                    escalated = True
                    root.set_attribute("triage.outcome", "escalated")
                    root.set_attribute("triage.turns",   turn)
                    print(f"\n  *** ESCALATED — {args.get('reason')} ***")

            if escalated:
                break


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

# Flush remaining spans and metrics before the process exits.
# Without this, the last batch may not be exported if the process ends
# before the background export thread fires.
_trace_provider.shutdown()
_meter_provider.shutdown()
