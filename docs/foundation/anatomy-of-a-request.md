# What's Actually in a Request?

"I only sent one sentence. Why did it use 1,000 tokens?"

This is one of the most common surprises people encounter. The answer: your one sentence is almost never all that's being sent. This page explains what actually goes into an AI request, and why token counts are often much higher than you'd expect.

## The parts of a request

Every call to an AI model is made up of a **messages array**. It can contain several different types of message:

### System prompt

The system prompt is a set of instructions that shapes how the model behaves. It's set by the application developer, not the end user, and it's invisible to the user.

A typical system prompt might say things like:
- "You are a helpful customer support assistant for Acme Corp."
- "Always respond in the same language the user writes in."
- "Never discuss competitors. If asked, politely redirect."
- "Format all responses as plain text. Do not use markdown."

System prompts can be short (a couple of sentences) or very long (hundreds of lines spelling out detailed behaviour, tone guidelines, product knowledge, and edge case handling). **Every word in the system prompt is paid for on every single request.**

### User messages

These are the messages the user actually typed. In a conversation, there will be one user message per turn.

### Assistant messages

These are the model's previous replies. In a multi-turn conversation, they're included so the model can remember what it already said.

### Tool definitions

If the model has tools available (like the ability to search the web, look up a database, or call an API), the description of those tools is included in the request. This can add hundreds of tokens per request, even if none of the tools get called.

## How it all adds up

Here's a realistic breakdown for a single message in a customer support chatbot:

<div class="dt-diagram">

```
┌─────────────────────────────────────────────────────────┐
│  Request to the AI model                                │
│                                                         │
│  System prompt                              ~600 tokens │
│  (behaviour rules, company info, tone)                  │
│                                                         │
│  Tool definitions (3 tools)                 ~300 tokens │
│  (search KB, create ticket, lookup order)               │
│                                                         │
│  Conversation history (5 previous turns)    ~400 tokens │
│  (what the user and AI already said)                    │
│                                                         │
│  User's current message: "where's my order?"  ~6 tokens │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│  Total input:                             ~1,306 tokens │
└─────────────────────────────────────────────────────────┘
```

</div>

The user typed 4 words. The model received 1,306 tokens, of which 99.5% came from overhead.

This isn't a flaw or inefficiency. It's just how LLMs work. The context is what gives the model the ability to answer helpfully and within the rules of the application. But it's important to understand when you're reasoning about costs.

## What you can do about it

**Ask whether you need an LLM at all.** If the output is predictable or rule-based, static code uses zero tokens and will always be faster and cheaper.

**Keep system prompts focused.** Every line you cut from the system prompt saves tokens on every single request. Audit yours periodically for instructions that no longer apply or that repeat each other.

**Be selective with tools.** Only include tool definitions the model actually needs for this conversation. If a tool is only relevant for certain query types, consider only including it when needed.

**Manage conversation history.** See the [Tokens](tokens.md) page for strategies: summarising old messages, starting new sessions for new topics, setting turn limits.

**Use caching.** The system prompt and tool definitions rarely change. Most providers will cache these and charge a reduced rate for repeated input. See [Tokens](tokens.md) for more on cached tokens.

## Why this matters for observability

When you instrument your AI calls with OpenTelemetry (as we do in [Step 2](../monitor-production/02-add-observability.md)), you'll see the actual token counts on every span. This is how you discover:

- Which endpoint or user type is sending the most tokens
- Whether a particular agent's system prompt has bloated over time
- Whether adding a new tool significantly increased per-request cost
- Whether conversation sessions are running too long before being reset

Observability replaces guesswork with exact data on where tokens are going.
