<div class="dt-hero">
  <h1>AI Observability with Dynatrace</h1>
  <p>Learn how to see inside your AI applications: track what they're doing, what they're costing, and when they go wrong.</p>
</div>

## Start here

A few concepts come up constantly in these tutorials. Spending 15 minutes here will make everything else click much faster.

| Topic | Why you need it |
|-------|----------------|
| [Tokens](foundation/tokens.md) | Everything AI charges are based on tokens. You can't understand cost data without this. |
| [What's in a Request](foundation/anatomy-of-a-request.md) | Why sending one sentence can cost 1,000 tokens. System prompts, history, tools, and how they add up. |
| [OpenTelemetry](foundation/opentelemetry.md) | The standard we use to collect data from AI apps. All our examples use it. |
| [AWS Bedrock](foundation/aws-bedrock.md) | The AI platform used in these tutorials. |

Then work through **[Setup](foundation/setup.md)** before running any code. The first thing it asks you to do is **fork this repository into your own GitHub account** — you don't have write access to the source, so you need your own copy before you can store secrets or use Codespaces. After that it walks you through credentials, environment options, and a smoke test.

!!! tip "Already familiar with OTel and Bedrock?"
    Skip straight to [Setup](foundation/setup.md), then pick a path below.

---

## Now pick your path

<div class="dt-cards">

<a href="monitor-production/" class="dt-card">
  <span class="dt-card-icon">🚀</span>
  <h3>AI in Production</h3>
  <p>You've built an app that calls an AI model. You want to monitor it: track costs, find slow calls, catch errors, and understand what the AI is actually doing.</p>
  <span class="dt-card-badge">Active tutorials</span>
</a>

<a href="monitor-development/" class="dt-card">
  <span class="dt-card-icon">🛠️</span>
  <h3>AI in Development</h3>
  <p>You're using AI tools (Copilot, Cursor, etc.) while writing code. You want to track how much AI tooling is being used and what it's costing your team.</p>
  <span class="dt-card-badge">Coming soon</span>
</a>

</div>
