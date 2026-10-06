"""
Customer support escalation demo.
Usage: python demo.py [complaint_id]   (default: runs all complaints)

Env vars required:
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
# Absolute path so agent files resolve correctly regardless of working directory
HERE = pathlib.Path(__file__).parent
MODEL = "openai.gpt-oss-120b"
ESCALATION_THRESHOLD = 4  # urgency >= this → hand off to human

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

    response = client.chat.completions.create(model=MODEL, messages=messages)
    return response.choices[0].message.content or ""


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

    # --- Agent 1: sentiment ---
    # Always runs first. Every complaint goes through sentiment scoring regardless
    # of content, because we need the urgency score before we can make any routing decision.
    # The sentiment agent returns JSON with urgency (1-5), sentiment label, and reasoning.
    # see .agents/sentiment.md
    raw = _call_agent("sentiment", message)
    try:
        assessment = json.loads(raw)
    except json.JSONDecodeError:
        assessment = {"urgency": 3, "sentiment": "unknown", "reasoning": raw}

    urgency = assessment.get("urgency", 3)
    print(f"\n  Urgency: {urgency}/5 — {assessment.get('sentiment')} — {assessment.get('reasoning')}")

    # --- Escalation gate ---
    # This is the only branching point in the pipeline. If urgency is high (legal threats,
    # bank disputes, repeated failures), we stop here and hand off to a human.
    # No policy check or draft is attempted — escalated complaints need human judgement,
    # not an automated response. triage.outcome on the root span records which path was taken.
    if urgency >= ESCALATION_THRESHOLD:
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
