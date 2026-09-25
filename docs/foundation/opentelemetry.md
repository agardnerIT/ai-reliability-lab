# OpenTelemetry

OpenTelemetry (often shortened to **OTel**) is the open standard for collecting observability data from applications. It's what we use to capture information about our AI calls and send it to Dynatrace.

## Signal types

Observability tools collect different types of data, called **signals**. OpenTelemetry supports traces, metrics, and logs, but there are others too, like events and profiles. Each signal type answers a different question about your system.

In these tutorials we focus on traces and metrics, as they're the most useful for understanding AI behaviour and cost. Here's a quick overview of the main types, with more emerging as the standard evolves:

### Traces

A **trace** is the complete story of one operation from start to finish. For example: diagnosing and routing a customer complaint email. That single operation might involve calling a sentiment agent, checking a policy database, and routing to the right team. The trace captures all of it as one joined-up picture.

A **span** is one step within that trace: "call the sentiment agent," "make this AI request," "look up the policy." Each span records:

- A name
- When it started and how long it took
- Whether it succeeded or failed
- Custom attributes (key-value pairs of extra information)

Spans nest inside each other, forming a tree. The top-level span is the **root span**. Everything inside it is a **child span**.

```
triage COMPLAINT-001                    ← root span (the whole operation)
  invoke_agent sentiment                ← child span (calling the sentiment agent)
    chat openai.gpt-oss-120b           ← grandchild span (the actual AI call)
  invoke_agent policy_checker           ← child span
    chat openai.gpt-oss-120b           ← grandchild span
```

This tree structure is incredibly useful for AI apps. You can see exactly which AI call took the longest, which one consumed the most tokens, and where errors occurred.

### Metrics

**Metrics** are numbers collected over time, aggregated rather than individual. They answer questions like:

- What's the average token usage per request?
- How many AI calls are we making per minute?
- What's the 95th percentile latency?

In our tutorials, we use a metric called `gen_ai.client.token.usage`, a histogram that tracks token counts across all AI calls, broken down by model, agent, and token type (input vs output).

### Logs

Logs are timestamped text records: "request received," "error: timeout," "user 123 logged in." Useful for debugging specific events. We don't focus on logs in these tutorials.

### Events

Events are a structured form of log, used to record discrete things that happened at a point in time. In AI workflows, an example would be recording each tool call an agent made during a run.

### Profiles

Profiles capture how your application is using resources (CPU, memory) over time. Useful for understanding the compute cost of your code, separate from the AI token cost.

### Others

The OpenTelemetry ecosystem is still growing. New signal types get added as the standard evolves.

## The OpenTelemetry Collector

Your application could send data directly to Dynatrace, and technically that works. But in these tutorials we route it through an **OpenTelemetry Collector** first. This is considered best practice for any modern enterprise observability stack.

<div class="dt-diagram">

```
Your App
    │
    │  OTLP (HTTP or gRPC)
    ▼
OTel Collector  ──────────────────►  Dynatrace
    │
    └── can also forward to other backends
```

</div>

The collector sits between your app and your backend. Using a collector has several practical benefits:

- Your app only needs to know one endpoint (the collector). Swap backends without touching app code.
- The collector can batch, filter, and transform data before it's sent.
- You can forward to multiple backends at once.
- You can run multiple collectors for redundancy.

In short: the collector decouples your application from your observability infrastructure. Change one without changing the other.

## The OTLP protocol

**OTLP** (OpenTelemetry Protocol) is how data travels between components. It works over HTTP or gRPC. In our examples, we use HTTP because it's simpler and works everywhere.

When you see these environment variables in the code:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Api-Token dt0c01.*****.***  # optional, only needed if your collector requires authentication
```

...the first one tells the app where the collector is, and the second one authenticates the connection.

## GenAI semantic conventions

OpenTelemetry defines standard attribute names for AI-related telemetry, called the [**GenAI semantic conventions**](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md). These are the `gen_ai.*` attributes you'll see throughout the tutorials:

| Attribute | What it records |
|-----------|----------------|
| `gen_ai.provider.name` | Which AI provider (e.g. `openai`, `anthropic`) |
| `gen_ai.operation.name` | What operation (`chat`, `invoke_agent`, `execute_tool`) |
| `gen_ai.request.model` | Model requested (e.g. `openai.gpt-oss-120b`) |
| `gen_ai.response.model` | Model that actually responded |
| `gen_ai.usage.input_tokens` | Input tokens consumed |
| `gen_ai.usage.output_tokens` | Output tokens generated |
| `gen_ai.agent.name` | Name of the agent (for multi-agent systems) |

Using standard names means Dynatrace (and other backends) can automatically recognise and visualise your AI telemetry without custom configuration.

!!! warning "Still in development"
    The GenAI semantic conventions are currently marked as **Development** status, which means the attribute names above may change as the spec matures. Check the [spec repo](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md) for the latest, and don't be surprised if a future version renames something.

## What you'll need

You'll need two things: **Docker** and a **Dynatrace environment**. If you don't have one, you can [start a free trial](https://dt-url.net/trial). We provide everything else.

Before starting the tutorials, we'll walk you through spinning up an OTel Collector locally using a Docker image we provide, pre-configured to forward data to your Dynatrace environment. The [Dynatrace Setup](dynatrace-setup.md) page has the exact commands. It takes a few minutes and you only need to do it once.
