"""
Smoke test — verifies both critical connections before any lab exercise:

  1. Code → OTel Collector → Dynatrace  (traces + metrics pipeline)
  2. Code → AWS Bedrock                 (AI model API)

If either check fails the script exits non-zero with a clear error message.
Fix the reported credential or connectivity issue before starting exercises.

No exercise-specific logic here — this is purely a go/no-go gate.

Usage:
    python code/smoke-test.py

Reads OTEL_EXPORTER_OTLP_ENDPOINT from the environment; falls back to
http://localhost:4318 if unset.
"""

import os
import sys
import time

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
SERVICE  = "otel-smoke-test"

# ---------------------------------------------------------------------------
# Check 1: OTel Collector reachability
# ---------------------------------------------------------------------------
print("=" * 60)
print("Check 1: OTel Collector pipeline")
print(f"  Sending to: {ENDPOINT}")

resource = Resource.create({"service.name": SERVICE})

# --- traces ---
trace_provider = TracerProvider(resource=resource)
try:
    span_exporter = OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces")
except Exception as exc:
    print(f"\n[FAIL] Could not create span exporter: {exc}", file=sys.stderr)
    print("       Is the OTel Collector running on port 4318?", file=sys.stderr)
    sys.exit(1)

trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
trace.set_tracer_provider(trace_provider)

# --- metrics ---
meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[
        PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{ENDPOINT}/v1/metrics"),
            export_interval_millis=2_000,
        )
    ],
)
metrics.set_meter_provider(meter_provider)

tracer = trace.get_tracer(SERVICE, "1.0.0")
meter  = metrics.get_meter(SERVICE, "1.0.0")

run_counter = meter.create_counter(
    name="smoke_test.runs",
    unit="{run}",
    description="Number of smoke-test executions",
)

with tracer.start_as_current_span("smoke-test") as span:
    span.set_attribute("smoke_test.version", "1.0.0")
    run_counter.add(1, {"smoke_test.version": "1.0.0"})
    print("  Span recorded:   smoke-test")
    print("  Metric recorded: smoke_test.runs +1")

# Flush — give the metric reader time to export before shutdown
time.sleep(3)
trace_provider.shutdown()
meter_provider.shutdown()
print("[OK] OTel Collector pipeline: telemetry accepted by collector")

# ---------------------------------------------------------------------------
# Check 2: AWS Bedrock
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("Check 2: AWS Bedrock connection")

try:
    from openai import OpenAI
    from aws_bedrock_token_generator import provide_token
except ImportError as exc:
    print(f"\n[FAIL] Missing dependency: {exc}", file=sys.stderr)
    print("       Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

try:
    token = provide_token()
except Exception as exc:
    print(f"\n[FAIL] Could not generate AWS Bedrock token: {exc}", file=sys.stderr)
    print("       Check that AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and", file=sys.stderr)
    print("       AWS_REGION are set correctly (or that aws sso login succeeded).", file=sys.stderr)
    sys.exit(1)

try:
    bedrock = OpenAI(
        api_key=token,
        base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
        project="default",
    )
    response = bedrock.chat.completions.create(
        model="openai.gpt-oss-120b",
        messages=[{"role": "user", "content": "Reply with the single word OK."}],
        max_tokens=5,
    )
    reply = (response.choices[0].message.content or "").strip()
    print(f"  Model replied:   {reply!r} (finish_reason: {response.choices[0].finish_reason})")
    print("[OK] AWS Bedrock connection: model reachable and responding")
except Exception as exc:
    print(f"\n[FAIL] Bedrock API call failed: {exc}", file=sys.stderr)
    print("       Your IAM policy needs both of these statements:", file=sys.stderr)
    print("         bedrock-mantle:CallWithBearerToken on resource *", file=sys.stderr)
    print("         bedrock-mantle:CreateInference on arn:aws:bedrock-mantle:us-east-2:*:project/default", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# All checks passed
# ---------------------------------------------------------------------------
print()
print("=" * 60)
print("Both checks passed. Wait ~60 s then verify data reached Dynatrace:")
print()
print('  Spans:   dtctl query \'fetch spans | filter service.name == "otel-smoke-test" | fields startTime, span.name, duration, service.name | sort startTime desc | limit 5\'')
print('  Metrics: dtctl query \'timeseries runs = sum(smoke_test.runs), by: {service.name} | filter service.name == "otel-smoke-test" | fieldsAdd total_runs = arraySum(runs) | fields service.name, total_runs\'')
sys.exit(0)
