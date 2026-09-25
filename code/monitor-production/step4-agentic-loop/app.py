"""
Customer support escalation demo — true agentic loop.

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

Usage: python app.py [complaint_id]   (default: runs all complaints)

Env vars:
  AWS_REGION   e.g. us-east-2
"""

import json
import pathlib
import sys

from openai import OpenAI
from aws_bedrock_token_generator import provide_token

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

    response = client.chat.completions.create(model=MODEL, messages=messages)
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Tool dispatcher — bridges model tool-call names to actual sub-agent calls
#
# _dispatch() is the boundary between the orchestrator's decision (a tool
# name + JSON arguments) and the implementation (a sub-agent LLM call or
# direct logic). The "escalate" tool is the only one that does NOT invoke
# an LLM — it simply returns a structured JSON result so the loop can detect
# it and halt.
# ---------------------------------------------------------------------------
def _dispatch(tool_name: str, args: dict) -> str:
    # Policy is loaded fresh each call so changes take effect without restart.
    policy = (HERE / "policy.md").read_text()

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

    turn = 0
    while True:
        turn += 1

        # tool_choice="auto" lets the model decide whether to call a tool or
        # produce a final text response. We never force a specific tool.
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]

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
