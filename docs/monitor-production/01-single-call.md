# Step 1: Your First AI Call

<div class="dt-trail">
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 1: First Call</span>
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
    <a href="06-streaming.md" class="dt-trail-step inactive">Step 6: Streaming</a>
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

We start with the most basic thing possible: a single question to an AI model.

## Before you start

Make sure your AWS credentials are configured. See [Environment Setup](../foundation/environment-setup.md) if you haven't done this yet.

## Running it

```bash
cd /workspace/code/monitor-production/step1and2-basic-app
python app.py
```

## The code

```python title="app.py"
from openai import OpenAI
from aws_bedrock_token_generator import provide_token

client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

response = client.chat.completions.create(
    model="openai.gpt-oss-120b",
    messages=[{"role": "user", "content": "What is Amazon Bedrock?"}],
)
print(response.choices[0].message.content)
```

Eight lines of meaningful code, excluding imports. Here is what each part does.

## What's happening here

### The client

```python
client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)
```

We're using the standard OpenAI Python library, but pointing it at AWS Bedrock's OpenAI-compatible endpoint (Bedrock Mantle). The `provide_token()` call handles AWS authentication, returning a short-lived credential that the OpenAI client uses as an API key.

See [AWS Bedrock](../foundation/aws-bedrock.md) for more on why we can use the OpenAI library here.

### The request

```python
response = client.chat.completions.create(
    model="openai.gpt-oss-120b",
    messages=[{"role": "user", "content": "What is Amazon Bedrock?"}],
)
```

This sends a **chat completion** request, the standard format for most AI model interactions. The `messages` array represents the conversation. Here it's just one user message, but it can grow to include full conversation history.

### The response

```python
print(response.choices[0].message.content)
```

The model returns `choices`, usually just one unless you ask for multiple completions. Each choice has a `message` with `role` (always `"assistant"` for model responses) and `content` (the actual text).

## What we're missing

Run this code and it works. You get a response. But you know nothing about:

- **How long did it take?** Was this fast or slow?
- **How many tokens did it use?** What did it cost?
- **Did it succeed?** What happens if it fails?
- **What did it actually say?** (Unless you print it, there's no record)

These are questions that matter in production. If this app handles 10,000 requests a day, you need to know when latency spikes, when costs are unusually high, and when the model starts returning errors.

[Step 2](../02-add-observability/) adds the instrumentation to capture all of this.

## What you should see

The model's answer to "What is Amazon Bedrock?", a paragraph or two explaining the service.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 2: Adding Observability →](02-add-observability.md)

We'll add OpenTelemetry to capture spans and metrics for this call.
