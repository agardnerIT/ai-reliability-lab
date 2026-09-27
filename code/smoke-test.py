"""
Smoke test — sends one trace span and one metric counter to the OTel Collector.
Run this after restarting the collector to confirm end-to-end plumbing works
before starting any lab exercise.

No LLM API key required.

Usage:
    python code/smoke-test.py

The script reads OTEL_EXPORTER_OTLP_ENDPOINT from the environment and falls
back to http://localhost:4318 if it is not set.
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

print(f"Sending to: {ENDPOINT}")

resource = Resource.create({"service.name": SERVICE})

# --- traces ---
trace_provider = TracerProvider(resource=resource)
trace_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{ENDPOINT}/v1/traces"))
)
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
    print("Span recorded:  smoke-test")
    print("Metric recorded: smoke_test.runs +1")

# Flush — give the metric reader time to export before shutdown
time.sleep(3)

trace_provider.shutdown()
meter_provider.shutdown()

print("Done. Wait ~60 s then verify with:")
print('  Spans:   dtctl query \'fetch spans | filter service.name == "otel-smoke-test" | limit 5\'')
print('  Metrics: dtctl query \'timeseries sum(smoke_test.runs), by:{service.name} | filter service.name == "otel-smoke-test"\'')
sys.exit(0)
