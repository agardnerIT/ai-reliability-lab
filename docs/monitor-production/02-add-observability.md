# Step 2: Adding Observability

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="01-single-call.md" class="dt-trail-step inactive">Step 1: First Call</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 2: Add OTel</span>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="03-agentic-pipeline.md" class="dt-trail-step inactive">Step 3: Pipeline</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="04-agentic-loop.md" class="dt-trail-step inactive">Step 4: Loop</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="05-streaming.md" class="dt-trail-step inactive">Step 5: Streaming</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="06-rag.md" class="dt-trail-step inactive">Step 6: RAG</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="07-guardrails.md" class="dt-trail-step inactive">Step 7: Guardrails</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="08-model-selection.md" class="dt-trail-step inactive">Step 8: Model Migration</a>
  </div>
</div>

We take the single-call app from Step 1 and add OpenTelemetry instrumentation so we can see what's happening inside Dynatrace.

## What we're adding

- A **trace** with a **span** wrapping the AI call
- Standard **GenAI attributes** on the span (model, token counts, finish reason)
- A **token usage metric** that aggregates across all calls

???+ question "Why not just use logs?"
    Logs are great for recording what happened, but they make it hard to answer questions like "how long did that AI call take?" or "which requests used the most tokens?" You'd have to parse text, join records by timestamp, and write your own aggregations.

    Spans give you structured, timed, correlated data by default. Each span has a start time, duration, and key-value attributes you can filter and aggregate in Dynatrace without any parsing. Metrics give you aggregated numbers over time without having to store every raw event.

    That said, logs and spans work well together. If your application already writes logs, you don't need to replace them. Spans add a layer on top that answers the questions logs can't answer efficiently.

    If you are starting from scratch, spans are probably all you need! After all, spans _are_ logs and it's also possible to add events to spans.

## Before you start

Make sure the OpenTelemetry collector is running. If you haven't started it yet, open a new terminal. Then customise the following variables and run:

```bash
export DT_TENANT=abc12345
export DT_API_TOKEN=dt0c01.*****.*******
```

Then start the collector:

```bash
docker run --rm \
  -p 4318:4318 \
  -e DT_TENANT \
  -e DT_API_TOKEN \
  -v $(pwd)/collector.config.yaml:/etc/otelcol-contrib/config.yaml \
  -v $(pwd)/file.log:/etc/file.log \
  otel/opentelemetry-collector-contrib:latest
```

Leave that terminal open. The collector needs to be running while you work through the steps below.

## Running it

```bash
cd code/monitor-production/step1and2-basic-app

pip install -r requirements.txt

export AWS_REGION=us-east-2
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

python app-instrumented.py
```

## The full instrumented code

```python title="app-instrumented.py"
import json

from openai import OpenAI
from aws_bedrock_token_generator import provide_token

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

# --- OTel setup ---
resource = Resource.create({"service.name": "bedrock-chat-client"})

provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

tracer = trace.get_tracer("bedrock-chat-client", "1.0.0")
meter = metrics.get_meter("bedrock-chat-client", "1.0.0")

# Token usage histogram (GenAI semantic convention)
token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)

# --- client ---
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

MODEL = "openai.gpt-oss-120b"
MESSAGES = [{"role": "user", "content": "What is Amazon Bedrock?"}]
operation = "chat"
span_name = f"{operation} {MODEL}"

with tracer.start_as_current_span(span_name) as span:
    # Set standard GenAI attributes on the span
    span.set_attribute("gen_ai.provider.name", "openai")
    span.set_attribute("gen_ai.operation.name", operation)
    span.set_attribute("gen_ai.request.model", MODEL)
    span.set_attribute("gen_ai.input.messages",
                       json.dumps([{"role": m["role"], "content": m["content"]}
                                   for m in MESSAGES]))

    response = client.chat.completions.create(model=MODEL, messages=MESSAGES)

    # Record response attributes
    span.set_attribute("gen_ai.response.model", response.model)
    span.set_attribute("gen_ai.response.finish_reasons",
                       [c.finish_reason for c in response.choices])

    if response.usage:
        span.set_attribute("gen_ai.usage.input_tokens", response.usage.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)

        common_attrs = {
            "gen_ai.provider.name":  "openai",
            "gen_ai.operation.name": operation,
            "gen_ai.request.model":  MODEL,
            "gen_ai.response.model": response.model,
        }
        token_usage.record(response.usage.prompt_tokens,
                           {**common_attrs, "gen_ai.token.type": "input"})
        token_usage.record(response.usage.completion_tokens,
                           {**common_attrs, "gen_ai.token.type": "output"})

    span.set_attribute("gen_ai.output.messages",
                       json.dumps([{
                           "role": c.message.role,
                           "content": c.message.content or "",
                           "finish_reason": c.finish_reason,
                       } for c in response.choices]))

    print(response.choices[0].message.content)

provider.shutdown()
meter_provider.shutdown()
```

Here is what each new piece does.

## Breaking it down

### The Resource

```python
resource = Resource.create({"service.name": "bedrock-chat-client"})
```

A **Resource** labels all the data from this process with a service name. Think of it as a name tag for your application.

When Dynatrace receives telemetry that includes `service.name`, it automatically creates a **service entity** with that name. This is the entity you'll see in the Services view, and it's what groups your traces, metrics, and any future spans from the same process together. You don't need to configure anything in Dynatrace for this to happen.

### TracerProvider and MeterProvider

```python
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)
```

These set up the OTel pipeline:

- `TracerProvider`: the factory that creates tracers. One per process.
- `BatchSpanProcessor`: buffers completed spans and exports them in the background. More efficient than sending one at a time.
- `OTLPSpanExporter`: sends spans to `OTEL_EXPORTER_OTLP_ENDPOINT` (your collector)
- `MeterProvider` / `PeriodicExportingMetricReader`: same idea for metrics, pushing on a regular interval

???+ info "Why shutdown() at the end?"
    Without `provider.shutdown()`, buffered spans that haven't been exported yet get lost when the process exits. The shutdown call flushes everything before the process terminates.

### The tracer and meter

```python
tracer = trace.get_tracer("bedrock-chat-client", "1.0.0")
meter = metrics.get_meter("bedrock-chat-client", "1.0.0")
```

These are the actual tools you use in your code to create spans and record metrics. The name and version appear in the **instrumentation scope** metadata of your telemetry.

### The token usage histogram

```python
token_usage = meter.create_histogram(
    name="gen_ai.client.token.usage",
    unit="{token}",
    description="Number of tokens used in a GenAI request",
)
```

A **histogram** tracks the distribution of values over time, not just the total but percentiles (p50, p95, p99). This is better than a counter for token usage because you want to know if some requests are outliers using 10x more tokens than average.

The name `gen_ai.client.token.usage` follows the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). Using standard names means Dynatrace can automatically recognise this metric without custom configuration.

### Wrapping the AI call in a span

```python
with tracer.start_as_current_span(span_name) as span:
    span.set_attribute("gen_ai.request.model", MODEL)
    # ...
    response = client.chat.completions.create(...)
    span.set_attribute("gen_ai.usage.input_tokens", response.usage.prompt_tokens)
```

The `with` block creates a span. The span starts when execution enters the block and ends when it exits. Everything between `with` and the closing indent is measured.

Attributes are key-value pairs attached to the span. We follow the GenAI semantic convention names so the data integrates cleanly with Dynatrace's AI Observability dashboards.

### Recording the metric

```python
token_usage.record(response.usage.prompt_tokens,
                   {**common_attrs, "gen_ai.token.type": "input"})
token_usage.record(response.usage.completion_tokens,
                   {**common_attrs, "gen_ai.token.type": "output"})
```

We record input and output tokens separately (two calls to `record`) so you can filter and chart them independently in Dynatrace.

## What you'll see in Dynatrace

After running, open Dynatrace and navigate to **Distributed Traces**. You should see a trace from `bedrock-chat-client` with:

- A single span named `chat openai.gpt-oss-120b`
- Duration showing the actual time the AI call took
- Attributes including token counts, model name, and the input/output messages

In **Metrics**, you'll find `gen_ai.client.token.usage` with dimensions for model, provider, and token type.

## What we're still missing

This is great for a single call, but real applications make many AI calls, sometimes in sequence, sometimes in parallel. We can't easily see the relationship between calls or understand the overall operation.

In [Step 3](03-agentic-pipeline.md), we build a multi-agent pipeline where multiple AI calls form a single business operation, and we observe them all together in one trace.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 3: Agentic Pipeline →](03-agentic-pipeline.md)
