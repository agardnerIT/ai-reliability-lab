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
    <a href="03-agentic-pipeline/" class="dt-trail-step">Step 3: Pipeline</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="04-agentic-loop/" class="dt-trail-step">Step 4: Loop</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="05-streaming/" class="dt-trail-step">Step 5: Streaming</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="06-rag/" class="dt-trail-step">Step 6: RAG</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="07-guardrails/" class="dt-trail-step">Step 7: Guardrails</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="08-model-selection/" class="dt-trail-step">Step 8: Model Migration</a>
  </div>
</div>

## Before you start

Complete [Foundation → Setup](../foundation/setup.md) before running any exercise. It walks you through:

- [ ] AWS credentials (no AWS CLI required — environment variables work)
- [ ] Dynatrace API token and platform token
- [ ] Choosing your environment (Codespaces, dev container, or plain Python)
- [ ] Verifying the OTel Collector is running on `localhost:4318`

!!! tip "Just want to read along?"
    You don't need to run the code to learn. All the key concepts are explained in the text.
