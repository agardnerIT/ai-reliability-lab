# Monitor AI in Production

This path walks you through adding observability to a real AI application, step by step.

We start with the simplest possible AI call (a single question to an AI model) and progressively add:

- OpenTelemetry instrumentation
- Multi-agent pipelines
- A fully autonomous agentic loop

Each step builds on the last. By the end, you'll be able to trace every AI call in a complex multi-agent system and see token costs, latencies, and outcomes in Dynatrace.

## The demo app

We use a **customer support triage system** as our example throughout. It receives customer complaints and either drafts a response or escalates to a human, using AI to make the decisions.

We chose this because it's realistic: most production AI apps involve more than one model call, have branching logic, and need to justify their decisions.

## Your journey

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="01-single-call/" class="dt-trail-step">Step 1: First Call</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="02-add-observability/" class="dt-trail-step">Step 2: Add OTel</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="03-guardrails/" class="dt-trail-step">Step 3: Guardrails</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="04-agentic-pipeline/" class="dt-trail-step">Step 4: Pipeline</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="05-agentic-loop/" class="dt-trail-step">Step 5: Loop</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="06-streaming/" class="dt-trail-step">Step 6: Streaming</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="07-rag/" class="dt-trail-step">Step 7: RAG</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="08-model-selection/" class="dt-trail-step">Step 8: Model Migration</a>
  </div>
</div>

## Steps at a glance

| # | Step | What you build | Key observability |
|---|------|---------------|-------------------|
| 1 | [First Call](01-single-call.md) | A single AI call with no instrumentation | None |
| 2 | [Add OTel](02-add-observability.md) | The same call, fully instrumented | 1 span, token histogram |
| 3 | [Guardrails](03-guardrails.md) | AWS Bedrock Guardrail blocking prompt injection | Guardrail block attribute + counter metric |
| 4 | [Pipeline](04-agentic-pipeline.md) | A fixed three-agent pipeline | Predictable nested spans |
| 5 | [Loop](05-agentic-loop.md) | A model-driven agentic loop | Variable nested spans |
| 6 | [Streaming](06-streaming.md) | Streaming response with time-to-first-chunk | 1 span, time-to-first-chunk metric |
| 7 | [RAG](07-rag.md) | Retrieval-augmented generation | retrieval + chat spans, chunk count metric |
| 8 | [Model Migration](08-model-selection.md) | Feature-flag-controlled A/B model routing | Per-model comparison metrics |

## Before you start

Complete [Foundation → Setup](../foundation/setup.md) before running any exercise. It walks you through:

- [ ] A `~/.aws/credentials` file (no AWS CLI required)
- [ ] Dynatrace API token and platform token
- [ ] Codespaces environment (see [Foundation → Setup](../foundation/setup.md))
- [ ] Verifying the OTel Collector is running on `localhost:4318`

!!! tip "Just want to read along?"
    You don't need to run the code to learn. All the key concepts are explained in the text.
