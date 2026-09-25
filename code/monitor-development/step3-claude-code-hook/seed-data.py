"""
Seed historical metric data for claude_code.tool.calls so that Davis AI
has enough data points to build a baseline and produce a forecast.

Sends 20 synthetic data points at 1-minute intervals over the past 20 minutes,
with realistic variation in tool call counts. One deliberate spike is included
so the forecast analyzer has something to detect.

Usage:
    export DT_ENDPOINT=https://<your-environment>.live.dynatrace.com
    export DT_API_TOKEN=<token-with-metrics.ingest-scope>
    python seed-data.py
"""

import os
import random
import time

import requests

DT_ENDPOINT = os.environ.get("DT_ENDPOINT", "").rstrip("/")
DT_API_TOKEN = os.environ.get("DT_API_TOKEN", "")

if not DT_ENDPOINT or not DT_API_TOKEN:
    raise SystemExit("Set DT_ENDPOINT and DT_API_TOKEN before running this script.")

INGEST_URL = f"{DT_ENDPOINT}/api/v2/metrics/ingest"

now_ms = int(time.time() * 1000)
interval_ms = 60 * 1000  # 1-minute buckets — matches Dynatrace's default metric resolution

# Realistic call counts per tool per minute of a typical coding session
tool_ranges = {
    "Bash":  (4, 12),
    "Read":  (6, 18),
    "Edit":  (2,  8),
    "Write": (1,  4),
}

lines = []
random.seed(42)  # reproducible spike position

for i in range(20, 0, -1):
    ts = now_ms - (i * interval_ms)
    session_id = "demo-session-baseline"

    for tool_name, (low, high) in tool_ranges.items():
        count = random.randint(low, high)

        # Introduce a spike at minute 5 to give the forecast something to flag
        if i == 5 and tool_name == "Bash":
            count = high * 5

        lines.append(
            f"claude_code.tool.calls,"
            f"tool.name={tool_name},"
            f"tool.status=success,"
            f"session.id={session_id},"
            f"dev.tool=claude-code "
            f"count,delta={count} {ts}"
        )

payload = "\n".join(lines)

resp = requests.post(
    INGEST_URL,
    headers={
        "Authorization": f"Api-Token {DT_API_TOKEN}",
        "Content-Type": "text/plain; charset=utf-8",
    },
    data=payload,
    timeout=10,
)

print(f"HTTP {resp.status_code}")
if resp.status_code == 202:
    print(f"Ingested {len(lines)} data points. Wait ~1 minute for Dynatrace to index them.")
else:
    print(resp.text)
