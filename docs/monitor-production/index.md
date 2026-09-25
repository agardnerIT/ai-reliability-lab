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
  </div>
</div>

## Before you start

Make sure you've read through the [Foundation](../foundation/index.md) section and have:

- [ ] A Dynatrace environment with a valid API token
- [ ] The OTel Collector running on `localhost:4318`
- [ ] Python 3.9+ installed
- [ ] AWS credentials configured for Bedrock Mantle access

See [Environment Setup](../foundation/environment-setup.md) for three ways to get all of this running, including a one-click GitHub Codespaces option that needs nothing installed locally.

!!! tip "Just want to read along?"
    You don't need to run the code to learn. All the key concepts are explained in the text.
