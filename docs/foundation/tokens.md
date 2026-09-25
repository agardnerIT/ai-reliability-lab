# Tokens

When you send text to an AI model, it doesn't see words the way you do. It breaks everything down into small pieces called **tokens**.

!!! danger "The key thing to understand"
    **Tokens = cost + response time.** Every token you send or receive gets charged for. Understanding tokens is understanding your AI bill.

## What is a token?

A token is roughly a word-fragment. Common short words like "the" or "is" are usually a single token. Longer or unusual words get split into pieces. Here's a rough guide:

- **1 token ≈ 4 characters** of English text
- **100 tokens ≈ 75 words**
- A typical short paragraph is around 50–100 tokens
- A detailed system prompt might be 500–1000 tokens

Different AI providers use different algorithms to break text into tokens, so the exact number varies between models. The ballpark is similar.

!!! example "A concrete example"
    The sentence *"Hello, how are you?"* is approximately **6 tokens**.

    The word *"observability"* is 1 token with most models (it's a known word). But an unusual technical term like *"gen_ai_usage_input_tokens"* might be split into 4–6 tokens.

## Three types of tokens

| Type | What it is | Who pays |
|------|-----------|---------|
| **Input tokens** | Text you send to the model (your prompt, system instructions, conversation history) | You |
| **Output tokens** | Text the model generates back | You (usually at a higher rate) |
| **Cached tokens** | Input tokens the provider has seen recently and stored, so they don't need to process them again | You, at a discount |

Output tokens typically cost 3–5x more than input tokens, because generating text is more compute-intensive than reading it.

???+ info "Cached tokens explained"
    If you send the same system prompt with every request (common in chatbots and agents), providers can recognise they've seen this text before and skip reprocessing it. You still pay, but at a reduced rate. Anthropic calls this "prompt caching"; OpenAI calls it "cached tokens". They're not free, but they're cheaper than regular input tokens. A useful discount if your system prompt runs long.

!!! tip "The golden rule"
    Fewer tokens sent and received = lower cost and faster responses. Everything else follows from that. Shorter prompts, shorter responses, less history, fewer tools. Every reduction directly reduces your bill and the time you wait for an answer.

## Prompt caching

Prompt caching lets a provider skip reprocessing text it has seen recently. If your system prompt is the same on every request, the provider can hold it in a short-lived cache and charge you a lower rate when it is reused. For long, stable system prompts this can be a meaningful cost reduction.

It is not a free win though, and it is not available everywhere.

### Not available on all models

Prompt caching is supported on a limited set of models. On AWS Bedrock, supported models include Anthropic Claude, Amazon Nova, and select OpenAI GPT models. Older models, smaller models, and any model accessed through the batch inference API do not support it.

The [AWS Bedrock prompt caching documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html) has the current list of supported models and their minimum token thresholds. If the content you want to cache is shorter than the threshold, caching is silently skipped with no error, no warning, and no cache hit.

### It does not switch on automatically

For most providers, you have to opt in explicitly. With Anthropic Claude and OpenAI GPT models on Bedrock, you must add `cache_control` markers to your request to tell the provider where the stable content ends. Without those markers, every request is treated as uncached regardless of how similar it is to the last one.

Amazon Nova is the exception: it applies caching automatically with no configuration required.

### Each provider handles it differently

!!! warning "Anthropic cache writes cost more than standard input"
    For Anthropic Claude models, the first time a prompt prefix is written to cache it is charged at a **higher** rate than a standard input token. You only save money if that cached content is reused enough times to offset the initial write cost. If your prompts vary significantly between requests, or if requests are spread more than five minutes apart, caching can cost more than it saves.

    The order of content in your request also matters. Anthropic processes cache in this sequence: `tools` first, then `system`, then `messages`. Changing anything in an earlier section invalidates the cache for everything that follows it, so stable content must always come before content that varies.

Other differences between providers:

| Provider | Default cache TTL | Configuration needed | Cache write cost |
|----------|--------------------|---------------------|-----------------|
| Anthropic Claude | 5 minutes (1 hour available on select models) | Explicit `cache_control` markers | Higher than standard input |
| Amazon Nova | Automatic | None | Included |
| OpenAI GPT-5.6 | 30 minutes | Explicit markers | Model-dependent |

One other thing worth knowing: cached read tokens do not count toward your AWS Bedrock token quota. Cache write tokens do. See the [AWS Bedrock token quota documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html) for how this affects concurrency and rate limits.

## Why conversation history compounds

Here's where costs can surprise people. Most AI apps maintain a conversation history and send the **entire thing** with every request.

<div class="dt-diagram">

```
Turn 1:   [System prompt] + [User: "Hello"]
                              ↓
          Response: "Hi there!"
                              
Turn 2:   [System prompt] + [User: "Hello"] + [AI: "Hi there!"] + [User: "What's the weather?"]
                              ↓
          Response: "I don't have access to weather data."

Turn 3:   [System prompt] + [User: "Hello"] + [AI: "Hi there!"] + [User: "What's the weather?"]
                          + [AI: "I don't have access..."] + [User: "Ok, tell me a joke"]
                              ↓
          Response: "Why did the..."
```

</div>

Each turn, the entire history goes back to the model. The input token count grows with every message. By turn 10 of a long conversation, you might be sending 5,000 tokens just to re-establish context before the model can reply.

This is why a chatbot that feels cheap to test can get expensive in production with real users having real conversations.

!!! info "Why is my token count so high?"
    If the numbers seem much larger than the text you sent, the answer is usually system prompts, conversation history, or tool definitions being sent alongside your message. See [What's Actually in a Request](anatomy-of-a-request.md) for a full breakdown.

### What you can do about it

- **Ask whether you need AI at all.** Static code is always faster and cheaper than an AI call. If the output is predictable or rule-based, just write the code.
- **Start a new session for each task.** Don't let a single conversation accumulate history across unrelated topics.
- **Use context compaction.** When the conversation gets long, replace old messages with a compact summary rather than sending the full history. Some tools (like Claude Code) do this automatically. The trade-off is a small loss of detail in exchange for significantly lower token counts.
- **Use system prompts efficiently.** Keep them as short as they need to be. Every word in a system prompt gets paid for on every single request.
- **Enable prompt caching** if your provider supports it and your system prompt doesn't change between requests.

## Pricing example

Pricing varies by model and provider. As a rough example:

| Token type | Typical cost |
|-----------|-------------|
| Input tokens | $0.50–$15 per million tokens |
| Output tokens | $1.50–$60 per million tokens |
| Cached input tokens | $0.10–$3.75 per million tokens |

???+ note "Want to see token counts for your own text?"
    OpenAI provides a tokenizer tool at [platform.openai.com/tokenizer](https://platform.openai.com/tokenizer). Type in any text and see exactly how it's broken up. Keep in mind different models tokenize slightly differently.

## What we track

In our tutorials, every AI call records:

- `gen_ai.usage.input_tokens`: tokens sent to the model
- `gen_ai.usage.output_tokens`: tokens generated by the model

These show up as both **span attributes** (on individual calls) and **metrics** (aggregated over time). You'll see how to capture them starting in [Step 2: Adding Observability](../monitor-production/02-add-observability.md).
