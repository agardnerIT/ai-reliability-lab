import json
import sys

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

resource = Resource.create({"service.name": "claude-code-session"})

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

meter = metrics.get_meter("claude-code-hook", "1.0.0")

tool_calls = meter.create_counter(
    name="claude_code.tool.calls",
    unit="{call}",
    description="Claude Code tool invocations, split by tool name and outcome",
)

# Passed by the hook registration: "success" (PostToolUse) or "failure" (PostToolUseFailure)
status = sys.argv[1] if len(sys.argv) > 1 else "success"

event = json.load(sys.stdin)

tool_name  = event.get("tool_name", "unknown")
session_id = event.get("session_id", "unknown")

tool_calls.add(1, {
    "tool.name":   tool_name,
    "tool.status": status,
    "session.id":  session_id,
    "dev.tool":    "claude-code",
})

# force_flush rather than shutdown — hooks are short-lived processes.
meter_provider.force_flush()

json.dump(event, sys.stdout)
sys.exit(0)
