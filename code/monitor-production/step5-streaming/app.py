"""
Customer support response demo — streaming output.

The key difference from a standard LLM call is stream=True: instead of
waiting for the complete response before doing anything, we receive and
print content chunks as they arrive. This is how production apps achieve
low perceived latency — the user sees words appearing immediately rather
than waiting for the full draft.

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

# The system prompt is intentionally simple — this example is about streaming
# mechanics, not multi-agent routing. The drafter just needs to produce a
# plausible customer support response.
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
    customer = complaint["customer"]
    message  = complaint["message"]

    print(f"\n{'='*60}")
    print(f"Complaint {complaint['id']} — {customer}")
    print(f"  \"{message}\"")
    print(f"\n  Streaming response:\n\n  ")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"Customer name: {customer}\nComplaint: {message}"},
    ]

    # stream=True returns an iterator of chunks rather than a single response object.
    # stream_options={"include_usage": True} asks the provider to emit token counts
    # on the final chunk — without this, usage is not available in streaming mode.
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    for chunk in stream:
        # Each chunk carries a delta — the incremental new content since the last chunk.
        # Not every chunk contains content (some carry finish_reason or usage only).
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)

    print("\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
# Reuse the shared complaints file from the agentic-loop example so this
# directory stays self-contained without duplicating fixture data.
complaints = json.loads((HERE / "complaints.json").read_text())

if len(sys.argv) > 1:
    target_id = sys.argv[1].upper()
    complaints = [c for c in complaints if c["id"] == target_id]
    if not complaints:
        print(f"Complaint {target_id} not found.")
        sys.exit(1)

for complaint in complaints:
    respond(complaint)
