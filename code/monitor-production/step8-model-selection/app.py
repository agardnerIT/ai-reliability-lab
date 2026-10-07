"""
Customer support response demo — model migration with OpenFeature.

Traffic is split between two models by a flagd feature flag. Edit flags.json
and flagd picks up the change within seconds — no restart needed. This is
how you run a controlled model migration: start at 0% challenger, watch
quality hold, then increment.

Usage: python app.py [complaint_id]   (default: runs all)

Env vars:
  AWS_REGION   e.g. us-east-2

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
# Urgency scoring — result gates flag routing
# ---------------------------------------------------------------------------
def _get_urgency(message: str) -> int:
    system_prompt = (HERE.parent / "step4-agentic-pipeline" / ".agents" / "sentiment.md").read_text()
    response = client.chat.completions.create(
        model=MODEL_CONTROL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": message},
        ],
    )
    try:
        return json.loads(response.choices[0].message.content or "").get("urgency", 3)
    except json.JSONDecodeError:
        return 3


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------
def triage(complaint: dict) -> None:
    cid      = complaint["id"]
    customer = complaint["customer"]
    message  = complaint["message"]

    # Score urgency first — high-urgency complaints always get the 120b model;
    # only low-urgency ones are eligible for the 20b challenger.
    urgency = _get_urgency(message)

    # Use the complaint ID as the targeting key so the same complaint always
    # routes to the same model variant — consistent assignment across runs.
    ctx     = EvaluationContext(targeting_key=cid, attributes={"urgency": urgency})
    details = flag_client.get_string_details("active-model", MODEL_CONTROL, ctx)
    model   = details.value
    variant = details.variant or "control"

    print(f"\n{'='*60}")
    print(f"Complaint {cid} — {customer}")
    print(f"  Urgency: {urgency}/5")
    print(f"  Model variant: {variant} ({model})")
    print(f"  \"{message}\"")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Customer name: {customer}\nComplaint: {message}"},
    ]

    response = client.chat.completions.create(model=model, messages=messages)
    draft    = response.choices[0].message.content or ""

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
