# Monitor AI in Development

Developers are using AI tools every day: IDE assistants, terminal agents, purpose-built scripts. Each interaction is an AI call with a cost, a latency, and a model. Almost none of it is measured.

This path shows you how to observe AI usage at development time, from a single instrumented script to a team-wide proxy that gives you per-developer cost attribution.

## The scenario

There is no fictional demo app here. The scenario is the developer workflow itself.

Developers on your team are using tools like Claude Code, GitHub Copilot, Cursor, and custom scripts to call AI models during their normal workday. Those calls go to Bedrock Mantle (or another provider). Your organisation pays for them. Right now, you probably have no idea how many calls are happening, which models are being used, or whether one person's heavy usage is quietly consuming most of the budget.

These five steps show you how to get that visibility.

## Your journey

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="01-invisible-cost/" class="dt-trail-step">Step 1: Invisible Cost</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="02-first-dev-span/" class="dt-trail-step">Step 2: Bedrock Telemetry</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="03-claude-code-hook/" class="dt-trail-step">Step 3: Harness Hooks</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="04-team-proxy/" class="dt-trail-step">Step 4: Enterprise Push</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="05-cost-attribution/" class="dt-trail-step">Step 5: AI Gateway</a>
  </div>
</div>

## Before you start

Complete [Foundation → Setup](../foundation/setup.md) before running any exercise. It walks you through:

- [ ] AWS credentials (no AWS CLI required — environment variables work)
- [ ] Dynatrace API token and platform token
- [ ] Codespaces environment (see [Foundation → Setup](../foundation/setup.md))
- [ ] Verifying the OTel Collector is running on `localhost:4318`

!!! tip "Just want to read along?"
    You don't need to run the code to learn. All the key concepts are explained in the text.
