# Step 8: Model Migration

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
    <a href="03-agentic-pipeline.md" class="dt-trail-step inactive">Step 3: Pipeline</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="04-agentic-loop.md" class="dt-trail-step inactive">Step 4: Loop</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="05-streaming.md" class="dt-trail-step inactive">Step 5: Streaming</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="06-rag.md" class="dt-trail-step inactive">Step 6: RAG</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="07-guardrails.md" class="dt-trail-step inactive">Step 7: Guardrails</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 8: Model Migration</span>
  </div>
</div>

Moving from one AI model to another is a common production decision. Maybe your current model is too expensive for what it does. Maybe a newer, cheaper model has launched and you want to know if it can handle your workload without degrading the experience. Either way, you cannot just flip a switch on day one. You need data to validate the move before committing.

This step shows how to run a controlled model migration: route a small percentage of real traffic to the new model while the existing one handles the rest, then use Dynatrace to compare cost, latency, and response quality between the two. When the data looks good, you increase the percentage. When you are confident, you complete the migration.

## The scenario

Your company has been using `openai.gpt-oss-120b` (the control model) to handle customer support complaints. It is reliable but expensive. The same model family has a smaller variant, `openai.gpt-oss-20b`, and you want to know if it can handle the job at lower cost without noticeably degrading responses.

The migration plan is:

| Phase | Traffic to challenger | Goal |
|---|---|---|
| 1 | 0% | Baseline: all traffic to control, establish reference metrics |
| 2 | 10% | Smoke test: confirm the challenger works at all |
| 3 | 50% | Head-to-head: enough data to compare properly |
| 4 | 100% | Complete the migration if metrics are acceptable |

At each phase, Dynatrace gives you the comparison. You are not guessing: you have a report.

## Running it

```bash
cd code/monitor-production/step7-model-selection

export AWS_REGION=us-east-2
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

python app-instrumented.py        # run all complaints
python app-instrumented.py C001   # run a specific complaint
```

No separate flag server to start. The app uses the official `openfeature-provider-flagd` package in file mode, which reads `flags.json` and polls for changes every five seconds. Edit the file and the next batch of complaints picks up the new split automatically.

## The flag

`flags.json` is the single place where the migration is controlled:

```json title="step7-model-selection/flags.json"
{
  "$schema": "https://flagd.dev/schema/v0/flags.json",
  "flags": {
    "active-model": {
      "state": "ENABLED",
      "variants": {
        "control":    "openai.gpt-oss-120b",
        "challenger": "openai.gpt-oss-20b"
      },
      "defaultVariant": "control",
      "targeting": {
        "if": [
          {"<=": [{"var": "urgency"}, 2]},
          {"fractional": [["control", 100], ["challenger", 0]]},
          "control"
        ]
      }
    }
  }
}
```

The flag has two variants: `control` (the existing model) and `challenger` (the new model). Before applying any split, the targeting rule checks the urgency score of the complaint. High-urgency complaints (score 3 or above) always go to the 120b control model. Only low-urgency complaints are eligible for the challenger. Within that low-urgency bucket, the `fractional` rule distributes traffic by percentage. Right now it is 100% control, 0% challenger. The migration has not started.

To move to phase 2, edit the percentages inside the `fractional` rule:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 90], ["challenger", 10]]},
  "control"
]
```

Save the file. The provider picks up the change within five seconds. The running app will start routing roughly 10% of low-urgency complaints to the challenger on the next requests.

### Why flagd and OpenFeature?

[OpenFeature](https://openfeature.dev/) is a CNCF standard for feature flag evaluation. Your application code calls the OpenFeature SDK; it does not call any flag provider directly. This means you can swap providers without touching the routing code. If your organisation already runs LaunchDarkly, Unleash, or Split, you point the SDK at that provider and the rest of the app is unchanged.

For this tutorial, the app uses the official `openfeature-provider-flagd` package configured in file mode. It reads `flags.json` directly with no server required. If you later move to a full flagd deployment, you switch to the gRPC resolver and keep the same `flags.json` without changes.

### Consistent routing

The `fractional` operator in flagd uses a hash of the targeting key to assign variants. The app passes the complaint ID as the targeting key, and the urgency score as a custom attribute:

```python
urgency = _get_urgency(message)
ctx     = EvaluationContext(targeting_key=cid, attributes={"urgency": urgency})
details = flag_client.get_string_details("active-model", MODEL_CONTROL, ctx)
```

The urgency score determines whether the complaint is even eligible for the challenger. The complaint ID determines which eligible complaints land in the challenger bucket. This means the same complaint always routes to the same model variant across multiple runs, which matters when you are re-running a batch to compare results.

## The routing code

```python title="step7-model-selection/app-instrumented.py"
urgency = _get_urgency(message)
ctx     = EvaluationContext(targeting_key=cid, attributes={"urgency": urgency})
details = flag_client.get_string_details("active-model", MODEL_CONTROL, ctx)
model   = details.value    # the model name to call
variant = details.variant  # "control" or "challenger"
```

`_get_urgency()` calls the sentiment agent and returns a score from 1 to 5. That score is passed to the flag as the `urgency` attribute. The flag targeting uses it to decide eligibility: scores above 2 always return `"control"`, regardless of the fractional split. `details.value` is the model name. The rest of the code passes `model` to the API call as normal.

## The instrumentation

### Feature flag attributes on the root span

```python
root.set_attribute("feature_flag.key",      "active-model")
root.set_attribute("feature_flag.variant",  variant)
root.set_attribute("feature_flag.provider", "flagd")
```

These follow the [OpenTelemetry semantic conventions for feature flags](https://opentelemetry.io/docs/specs/semconv/feature-flags/). Putting them on the root span means you can filter all traces by variant at the top level in Dynatrace without drilling into child spans.

### Feature flag variant on the token metric

```python
token_usage.record(response.usage.prompt_tokens, {
    ...
    "feature_flag.variant": variant,
})
```

Adding `feature_flag.variant` as a dimension on the token histogram means you can split the cost metric by variant directly. One chart, two lines: control token cost vs challenger token cost.

### The routing counter

```python
model_requests = meter.create_counter(
    name="gen_ai.model_selection.requests",
    unit="{request}",
    description="Requests routed to each model variant",
)

model_requests.add(1, {
    "feature_flag.key":     "active-model",
    "feature_flag.variant": variant,
    "gen_ai.request.model": model,
})
```

This answers a question you must answer before reading quality metrics: **is the split working?**

If you set challenger to 10% and run 50 complaints, you expect roughly 5 in the challenger bucket. If you see 0, the flag is not being evaluated. If you see 50, the targeting rule is wrong. Only once the counter confirms the split is correct do the quality comparisons mean anything.

## Running the migration

**Phase 1: establish a baseline**

With `flags.json` at 100% control, run the full complaint set. All traces will have `feature_flag.variant = "control"`. This gives you reference values for latency and cost with no challenger traffic. Write them down. You will compare against these numbers in later phases.

**Phase 2: 10% challenger**

Edit the `fractional` percentages in `flags.json`:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 90], ["challenger", 10]]},
  "control"
]
```

The provider picks this up within five seconds. Run the complaints again. In Dynatrace, check `gen_ai.model_selection.requests` first. You should see roughly 90/10 in the counter for low-urgency complaints; high-urgency complaints will only appear under `"control"`. If the split looks right, then compare:

- `gen_ai.usage.input_tokens` split by `feature_flag.variant`: are input costs similar?
- `gen_ai.usage.output_tokens` split by `feature_flag.variant`: is the challenger more verbose or more terse?
- Span duration split by `feature_flag.variant`: is the challenger faster or slower?

**Phase 3: 50/50**

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 50], ["challenger", 50]]},
  "control"
]
```

With equal traffic, the comparison is head-to-head. This is where you read the response content in the traces (`gen_ai.output.messages`) and make a qualitative judgement: are the challenger responses as useful as the control?

**Phase 4: complete the migration**

If the challenger looks good at 50%, complete the migration:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 0], ["challenger", 100]]},
  "control"
]
```

Or, if you want to keep a clean record, flip `defaultVariant` to `"challenger"` and remove the targeting rule entirely. The traces continue to carry `feature_flag.variant = "challenger"` so the migration is recorded in your observability data.

## What you'll see in Dynatrace

Each trace has three spans. The root `triage` span carries:

- `complaint.id` and `complaint.customer`
- `complaint.urgency`: the score from 1 to 5
- `feature_flag.key = "active-model"`
- `feature_flag.variant`: either `"control"` or `"challenger"`
- `feature_flag.provider = "flagd"`

The child `invoke_agent sentiment` span (and its nested `chat` span) records the urgency scoring call. The second child `chat` span carries the standard GenAI attributes for the response:

- `gen_ai.request.model`: the actual model that handled this request
- `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`
- `gen_ai.output.messages`: the full response text

**Traces view:** Filter by `feature_flag.variant = "challenger"` to see only the challenger traces. Compare their duration against the same filter for `"control"`. This is the latency comparison.

**Metrics view:** Chart `gen_ai.client.token.usage` split by `feature_flag.variant`. Two lines: one for each model tier. The gap between them is your potential cost saving (or the cost of a quality upgrade, if the challenger is larger).

**Routing verification:** `gen_ai.model_selection.requests` split by `feature_flag.variant` confirms the actual distribution matches your flag configuration. Always check this before drawing conclusions from quality metrics.

## The report

After phase 3, you have the data to make the call. The comparison in Dynatrace looks something like this:

| Metric | Control | Challenger |
|---|---|---|
| Avg input tokens | 312 | 308 |
| Avg output tokens | 187 | 152 |
| Avg latency | 2.4s | 1.1s |
| Requests | 50 | 50 |

The challenger uses fewer output tokens (cheaper) and responds faster. The question is whether the shorter output means the quality is worse. That judgment comes from reading the `gen_ai.output.messages` content in the traces alongside the numbers. Dynatrace gives you both in the same place.

This is the report you take to the meeting: cost, latency, and response quality, drawn from real production traffic.

## Summary

| | What's new |
|---|---|
| **Step 1–7** | Observability on a fixed model, including guardrail monitoring |
| **Step 8** | Feature-flag-controlled model routing + comparison metrics |

The instrumentation pattern is the same as all previous steps. What changes is that `gen_ai.request.model` now varies across traces, and `feature_flag.*` attributes tell you why. Everything else carries forward unchanged: spans, histograms, OTel semantic conventions.

<div id="dt-quiz-anchor"></div>

## What's next?

That's the last step in the Monitor Production track. Head back to the [Monitor Production AI](index.md) overview, or continue with [Monitor AI in Development](../monitor-development/index.md).
