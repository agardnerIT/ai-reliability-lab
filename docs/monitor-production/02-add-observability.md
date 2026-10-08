# Step 2: Adding Observability

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="../01-single-call/" class="dt-trail-step inactive">Step 1: First Call</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 2: Add OTel</span>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../03-guardrails/" class="dt-trail-step inactive">Step 3: Guardrails</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../04-agentic-pipeline/" class="dt-trail-step inactive">Step 4: Pipeline</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../05-agentic-loop/" class="dt-trail-step inactive">Step 5: Loop</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../06-streaming/" class="dt-trail-step inactive">Step 6: Streaming</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../07-rag/" class="dt-trail-step inactive">Step 7: RAG</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../08-model-selection/" class="dt-trail-step inactive">Step 8: Model Migration</a>
  </div>
</div>

We take the single-call app from Step 1 and add OpenTelemetry instrumentation so we can see what's happening inside Dynatrace.

## What we're adding

- A **trace** with a **span** wrapping the AI call
- Standard **[GenAI attributes](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md)** on the span (model, token counts, finish reason)
- A **token usage metric** that aggregates across all calls

???+ question "Why not just use logs?"
    Logs are great for recording what happened, but they make it hard to answer questions like "how long did that AI call take?" or "which requests used the most tokens?" You'd have to parse text, join records by timestamp, and write your own aggregations.

    Spans give you structured, timed, correlated data by default. Each span has a start time, duration, and key-value attributes you can filter and aggregate in Dynatrace without any parsing. Metrics give you aggregated numbers over time without having to store every raw event.

    That said, logs and spans work well together. If your application already writes logs, you don't need to replace them. Spans add a layer on top that answers the questions logs can't answer efficiently.

    If you are starting from scratch, spans are probably all you need! After all, spans _are_ logs and it's also possible to add events to spans.

## Before you start

The OTel Collector starts automatically alongside your Codespace. You don't need to run anything.

To point it at your Dynatrace tenant, follow the [Adding your Dynatrace token](../foundation/environment-setup.md#adding-your-dynatrace-token) steps in Environment Setup if you haven't already.

## Running it

```bash
cd /workspace/code/monitor-production/step1and2-basic-app
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

After running, wait about **60 seconds** for data to arrive, then query from the terminal.

### Check the trace

```bash
dtctl query 'fetch spans
| filter service.name == "bedrock-chat-client"
| fields start_time, span.name, duration, gen_ai.request.model, gen_ai.usage.input_tokens, gen_ai.usage.output_tokens
| sort start_time desc
| limit 5'
```

You should see a row with `span.name = chat openai.gpt-oss-120b`, the actual duration of the AI call, and your token counts.

### Check the metric

```bash
dtctl query 'timeseries tokens = sum(gen_ai.client.token.usage), by: {gen_ai.token.type, gen_ai.request.model}
| filter gen_ai.request.model == "openai.gpt-oss-120b"
| fieldsAdd total = arraySum(tokens)
| fields gen_ai.request.model, gen_ai.token.type, total'
```

You should see two rows with a plain token count — one for `input` and one for `output`.

???+ info "Why arraySum?"
    `timeseries` returns one value per time bucket across the full lookback window (default ~2 hours), so the `tokens` column is an array. `arraySum()` collapses that array into a single total.

## What we're still missing

You can now see every call your application makes. But visibility alone doesn't stop a user from making the model do something it shouldn't — that's a safety concern, not an observability one, and it exists from the very first call this app makes.

In [Step 3](03-guardrails.md), before we grow the app into more complex call patterns, we add an AWS Bedrock Guardrail and instrument it so blocked requests are just as visible as successful ones.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 3: Guardrails →](03-guardrails.md)
