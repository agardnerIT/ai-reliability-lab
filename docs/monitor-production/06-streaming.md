# Step 6: Streaming

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="01-single-call.md" class="dt-trail-step inactive">Step 1: First Call</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="02-add-observability.md" class="dt-trail-step inactive">Step 2: Add OTel</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="03-guardrails.md" class="dt-trail-step inactive">Step 3: Guardrails</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="04-agentic-pipeline.md" class="dt-trail-step inactive">Step 4: Pipeline</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="05-agentic-loop.md" class="dt-trail-step inactive">Step 5: Loop</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 6: Streaming</span>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="07-rag.md" class="dt-trail-step inactive">Step 7: RAG</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="08-model-selection.md" class="dt-trail-step inactive">Step 8: Model Migration</a>
  </div>
</div>

Streaming changes how the model sends its response. Instead of waiting for the entire reply before returning anything, the model sends tokens as it generates them. Your application can display them in real time.

This changes the instrumentation pattern in three important ways.

## Running it

```bash
cd /workspace/code/monitor-production/step6-streaming

export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

python app-instrumented.py        # run all complaints
python app-instrumented.py C001   # run a specific complaint
```

## What changes

In every previous step, the response was a single object returned all at once. You could read `response.usage`, `response.choices[0].finish_reason`, and `response.choices[0].message.content` immediately after the call returned.

With streaming, there is no single response object. Instead you iterate over a stream of small chunks. Each chunk carries a fragment of the content, and the final chunk carries the token counts. This means:

1. **The span must stay open for the full stream.** You cannot record token counts or finish reason until you have consumed all chunks. Those attributes are deferred to after the loop ends.

2. **Time-to-first-chunk must be measured with a wall-clock timer.** This is a new metric that does not exist in non-streaming calls. It is also how humans judge whether an LLM feels responsive: not how long the full response takes, but how quickly the first word appears. A model that starts writing in half a second feels fast even if the complete reply takes ten seconds. One that sits silent for five seconds feels broken, even if it finishes quickly after that.

3. **Token usage arrives on a final empty chunk.** The provider sends a terminating chunk with no content but with `chunk.usage` populated. This only happens if you set `stream_options={"include_usage": True}` on the request.

## The instrumentation

### The span wraps the iteration loop

```python
with tracer.start_as_current_span(f"chat {MODEL}") as span:
    span.set_attribute("gen_ai.request.stream", True)
    # ... other request attributes ...

    start = time.perf_counter()
    first_chunk_elapsed: float | None = None

    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
    )

    content_chunks: list[str] = []
    finish_reason: str | None = None

    for chunk in stream:
        ...  # see sections below

    # --- Deferred attributes: set after the loop ends ---
    span.set_attribute("gen_ai.response.finish_reasons", ...)
    span.set_attribute("gen_ai.output.messages", ...)
```

The span opens before the stream starts and closes after the loop ends. This means the span duration is the total time to receive the complete response, which is the correct end-to-end latency for a streaming call.

### Measuring time-to-first-chunk

```python
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        if first_chunk_elapsed is None:
            first_chunk_elapsed = time.perf_counter() - start
        delta = chunk.choices[0].delta.content
        content_chunks.append(delta)
        print(delta, end="", flush=True)
```

The timer starts just before the stream opens (before any network round-trip) and stops on the first chunk that carries content. The result is recorded as both a span attribute and a metric after the loop ends:

```python
if first_chunk_elapsed is not None:
    span.set_attribute("gen_ai.response.time_to_first_chunk", first_chunk_elapsed)
    ttfc.record(first_chunk_elapsed, {
        "gen_ai.provider.name":  "openai",
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model":  MODEL,
    })
```

???+ info "Why does time-to-first-chunk matter?"
    Streaming only feels fast if the first token arrives quickly. A five-second silence before streaming starts is indistinguishable from a broken request to the person waiting for it.

    A slow time-to-first-chunk is usually a cold-start or scheduling delay on the provider side, not something related to the length of the response. The span duration tells you total time; time-to-first-chunk tells you where the initial wait actually is.

### Collecting token usage from the final chunk

```python
for chunk in stream:
    # ...content chunks handled above...

    if chunk.usage:
        span.set_attribute("gen_ai.usage.input_tokens",  chunk.usage.prompt_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", chunk.usage.completion_tokens)
        metric_attrs = {
            "gen_ai.provider.name":  "openai",
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model":  MODEL,
        }
        token_usage.record(chunk.usage.prompt_tokens,
                           {**metric_attrs, "gen_ai.token.type": "input"})
        token_usage.record(chunk.usage.completion_tokens,
                           {**metric_attrs, "gen_ai.token.type": "output"})
```

`chunk.usage` is only populated on the final chunk, and only because we passed `stream_options={"include_usage": True}`. Without that option, token counts are unavailable in streaming mode and `gen_ai.usage.*` cannot be set on the span.

### The new metric

```python
ttfc = meter.create_histogram(
    name="gen_ai.client.operation.time_to_first_chunk",
    unit="s",
    description="Time from request to first content chunk",
)
```

This follows the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) for streaming. Use the p50 to understand typical model startup latency and the p99 to catch outliers caused by provider-side cold starts or scheduling delays.

## What you'll see in Dynatrace

After running, wait about **60 seconds** for data to arrive, then query from the terminal.

Each trace will have a single `chat` span whose duration is the full streaming time. On that span you will see:

- `gen_ai.request.stream: true` confirming this was a streaming call
- `gen_ai.response.time_to_first_chunk`: how long before content started arriving
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` from the final chunk
- `gen_ai.output.messages` containing the assembled full response

In **Metrics**, you will find two histograms:

- `gen_ai.client.token.usage` (the same one from Step 2, now populated from streaming)
- `gen_ai.client.operation.time_to_first_chunk` (streaming-specific, in seconds)

### Check the streaming spans

```bash
dtctl query 'fetch spans
| filter service.name == "support-streaming"
| filter gen_ai.operation.name == "chat"
| fieldsAdd dur_ns = toLong(duration)
| fieldsAdd duration_readable = concat(toString(tolong(dur_ns / 60000000000)), "m ", toString(round((dur_ns / 1000000000) - (tolong(dur_ns / 60000000000) * 60), decimals:1)), "s")
| fields start_time, trace.id, span.name, duration_readable, gen_ai.response.time_to_first_chunk, gen_ai.usage.input_tokens, gen_ai.usage.output_tokens
| sort start_time desc
| limit 10'
```

Each row is one streaming call. The `span.name` will be `chat openai.gpt-oss-120b` and its parent root span is `respond {complaint_id}` — use `trace.id` to link them. Compare `gen_ai.response.time_to_first_chunk` (in seconds) against `duration_readable` (total time). A small TTFC relative to the total means the model started generating quickly — most of the time was spent streaming tokens. A large TTFC means the model was slow to start.

### Check time-to-first-chunk over time

```bash
dtctl query 'timeseries ttfc = avg(gen_ai.client.operation.time_to_first_chunk), by: {gen_ai.request.model}
| fieldsAdd avg_ttfc = arrayAvg(ttfc)
| fields gen_ai.request.model, avg_ttfc'
```

### Check token usage

```bash
dtctl query 'timeseries tokens = sum(gen_ai.client.token.usage), by: {gen_ai.token.type}
| fieldsAdd total = arraySum(tokens)
| fields gen_ai.token.type, total'
```

Compare `time_to_first_chunk` against span duration across complaints. If the first-chunk time is consistently close to the total duration, the model is generating quickly but you have network or streaming overhead. If it is high relative to the total, the model is slow to start.

## What's next?

So far, every example has given the model everything it needs directly in the prompt. That works when the background knowledge is small. But real products have product catalogues, policy documents, knowledge bases, and FAQs that are far too large to include on every request.

RAG (Retrieval-Augmented Generation) solves this. Instead of stuffing the whole document into the prompt, you search it first and pass only the relevant sections to the model. Your knowledge base can be thousands of pages and the model never has to see more than a handful at a time.

In [Step 7](07-rag.md), we add a retrieval step to the trace. A vector search runs before the LLM call, and the results feed directly into the prompt. This introduces a new span type, a new metric, and a new question you can answer from your traces: what context did the model actually see?

<div id="dt-quiz-anchor"></div>

## Next step

[Step 7: RAG →](07-rag.md)
