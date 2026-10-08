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
    <span class="dt-trail-step">Step 8: Model Migration</span>
  </div>
</div>

Moving from one AI model to another is a common production decision. Maybe your current model is too expensive for what it does. Maybe a newer, cheaper model has launched and you want to know if it can handle your workload without degrading the experience. Either way, you cannot just flip a switch on day one. You need data to validate the move before committing.

This step shows how to run a controlled model migration: route a small percentage of real traffic to the new model while the existing one handles the rest, then use Dynatrace to compare cost, latency, and response quality between the two. When the data looks good, you increase the percentage. When you are confident, you complete the migration.

## The scenario

Your company has been using `openai.gpt-oss-120b` (the control model) to handle customer support complaints. It is reliable but expensive. The same model family has a smaller variant, `openai.gpt-oss-20b`, and you want to know if it can handle the job at lower cost without noticeably degrading responses.

The migration plan is:

| Phase | Split (control / challenger) | Complaints | Goal |
|---|---|---|---|
| 1 | 100 / 0 | C001 to C025 | Baseline: all traffic to control, establish reference metrics |
| 2 | 80 / 20 | C026 to C050 | Smoke test: confirm the challenger works at all |
| 3 | 50 / 50 | C051 to C075 | Head-to-head: enough data to compare properly |
| 4 | 20 / 80 | C076 to C100 | Near-complete migration: confirm the results hold at scale |

You do this in a single run. You start the app once and move through the phases by editing `flags.json` by hand while it runs. Each step exposes more traffic to the challenger only after the previous one looked healthy. If a step goes wrong, put the percentages back: the flag is your rollback. Dynatrace gives you the comparison at every point. You are not guessing: you have a report.

## Running it

```bash
cd /workspace/code/monitor-production/step8-model-selection
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

python app-instrumented.py        # run all 100 complaints
python app-instrumented.py C001   # run a specific complaint
```

This step uses 100 complaints instead of the usual handful, because a percentage split only shows up in the data when there is enough traffic to split. Each complaint makes two model calls, so a full run takes several minutes.

**You start the app once and run all 100 complaints in a single run.** While it is running, **you** change the traffic split by editing `flags.json` by hand. The app does not change the split for you. The [Running the migration](#running-the-migration) section tells you exactly when to make each edit.

Because you need to edit a file while the app is busy, open two terminals (or one terminal and your editor):

- **Terminal 1:** start `python app-instrumented.py` and leave it running. It prints `Complaint C001`, `Complaint C002` and so on as it goes. You use these lines to know when to make an edit.
- **Terminal 2 or your editor:** edit and save `flags.json` when the run reaches each checkpoint.

No separate flag server to start. The app uses the official `openfeature-provider-flagd` package in file mode, which reads `flags.json` and polls for changes every five seconds. Save the file and the next complaint to be evaluated picks up the new split automatically. You do not restart the app.

## The flag

`flags.json` is the single place where the migration is controlled:

```json title="step8-model-selection/flags.json"
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
  {"fractional": [["control", 80], ["challenger", 20]]},
  "control"
]
```

Save the file. The provider picks up the change within five seconds. The running app will start routing roughly 20% of low-urgency complaints to the challenger on the next complaints it evaluates.

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

```python title="step8-model-selection/app-instrumented.py"
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

If you set challenger to 20% and the run is at C040, you expect roughly 3 complaints in the challenger bucket so far (20% of the 15 or so low-urgency complaints in C026 to C040). If you see 0 after several complaints, the flag edit has not been picked up. If you see challenger requests on high-urgency complaints, the targeting rule is wrong, because those should never reach the challenger. Only once the counter confirms the split is correct do the quality comparisons mean anything.

## Running the migration

Start the app **once** and leave it running for all 100 complaints. You make the changes to `flags.json` yourself, by hand, at the checkpoints below. Nothing edits the file for you.

Only the 60 or so low-urgency complaints are eligible for the challenger. The flag decides by the complaint ID, so the numbers below are approximate, and your run will be close to them but not identical:

| Phase | Split | Complaints | Challenger requests | Control requests |
|---|---|---|---|---|
| 1 | 100 / 0 | C001 to C025 | 0 | 25 |
| 2 | 80 / 20 | C026 to C050 | about 3 | about 22 |
| 3 | 50 / 50 | C051 to C075 | about 7 | about 18 |
| 4 | 20 / 80 | C076 to C100 | about 12 | about 13 |

Because the same complaint always routes to the same variant, a complaint that lands in the challenger bucket stays there as you raise the percentage. Each phase adds more complaints to the challenger, so you are always comparing like with like.

!!! warning "You must edit `flags.json` yourself"
    The app never changes the split on its own. If you do nothing, every complaint goes to the control model and you will never see the challenger. Watch Terminal 1 for the `Complaint C0xx` lines and make each edit when the run reaches the checkpoint.

**Start the run**

In Terminal 1:

```bash
python app-instrumented.py
```

Leave it running. Open Dynatrace alongside it (see [Watching the shift live](#watching-the-shift-live)) so you can see each change land.

**Phase 1 (C001 to C025): establish a baseline**

`flags.json` starts at 100% control, so no edit is needed. All traces have `feature_flag.variant = "control"`. This gives you reference values for latency and cost with no challenger traffic. Write them down. You will compare against these numbers in later phases.

**Phase 2 (C026 to C050): 80 / 20**

When Terminal 1 shows `Complaint C026`, edit the `fractional` percentages in `flags.json` and save:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 80], ["challenger", 20]]},
  "control"
]
```

The provider picks this up within five seconds. Do not restart the app. Within a few complaints, the terminal starts printing `Model variant: challenger (openai.gpt-oss-20b)` for some low-urgency complaints. In Dynatrace, check `gen_ai.model_selection.requests` first. You should see roughly 80/20 in the counter for low-urgency complaints; high-urgency complaints will only appear under `"control"`. If the split looks right, then compare:

- `gen_ai.usage.input_tokens` split by `feature_flag.variant`: are input costs similar?
- `gen_ai.usage.output_tokens` split by `feature_flag.variant`: is the challenger more verbose or more terse?
- Span duration split by `feature_flag.variant`: is the challenger faster or slower?

At 20% the question is only "does it work?" Look for errors and obvious problems, not fine differences. If anything looks wrong, set the split back to `100 / 0` and nothing else changes.

**Phase 3 (C051 to C075): 50 / 50**

When Terminal 1 shows `Complaint C051`, edit and save `flags.json` again:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 50], ["challenger", 50]]},
  "control"
]
```

With equal traffic, the comparison is head-to-head. Verify the counter shows roughly 50/50 for low-urgency complaints, then repeat the same three comparisons. This is also where you read the response content in the traces (`gen_ai.output.messages`) and make a qualitative judgement: are the challenger responses as useful as the control?

**Phase 4 (C076 to C100): 20 / 80**

When Terminal 1 shows `Complaint C076`, edit and save `flags.json` one last time:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 20], ["challenger", 80]]},
  "control"
]
```

You are checking that what you saw at 20% and 50% still holds with most of the low-urgency traffic on the challenger: the same token pattern, the same latency gap, and no new errors. Let the run finish.

**After the run: complete the migration**

If the challenger looks good, completing the migration means setting the split to 0 / 100:

```json
"if": [
  {"<=": [{"var": "urgency"}, 2]},
  {"fractional": [["control", 0], ["challenger", 100]]},
  "control"
]
```

Or, if you want to keep a clean record, flip `defaultVariant` to `"challenger"` and remove the targeting rule entirely. The traces continue to carry `feature_flag.variant = "challenger"` so the migration is recorded in your observability data.

Before running the lab again, set `flags.json` back to `100 / 0`.

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

## Watching the shift live

Because you change the split during one run, the best way to see the migration is a time series. Each chart below shows the challenger appearing when you save `flags.json`, then growing at each phase. Run these with `dtctl query`, or paste the DQL into a Dashboards tile or a Notebook. Set the timeframe to the last 30 minutes and refresh while the app runs.

!!! note
    The service name is `support-model-selection`. The `chat` span for the draft response does not carry `feature_flag.variant`, so these queries group by `gen_ai.request.model` instead. That is the same split: `openai.gpt-oss-120b` is the control and `openai.gpt-oss-20b` is the challenger. The urgency scoring call also uses a `chat` span, and always uses the control model. The queries exclude it by filtering out spans with a `gen_ai.agent.name`.

### Traffic split over time

This is the headline chart. Use a stacked area or bar chart.

```bash
dtctl query 'fetch spans
| filter service.name == "support-model-selection"
| filter transaction.is_root_span == true
| filter isNotNull(feature_flag.variant)
| makeTimeseries requests = count(), by: {feature_flag.variant}, interval: 30s'
```

At first you see only `control`. After the phase 2 edit a `challenger` series appears, and it takes over the chart by phase 4.

### Challenger share (%) over time

Use a line chart with a single line that climbs as you raise the percentage. This one shows only low-urgency complaints, because those are the only ones eligible for the challenger.

```bash
dtctl query 'fetch spans
| filter service.name == "support-model-selection"
| filter transaction.is_root_span == true
| filter complaint.urgency <= 2
| makeTimeseries
    total = count(),
    challenger = countIf(feature_flag.variant == "challenger"),
    interval: 1m
| fieldsAdd challenger_pct = challenger[] / total[] * 100
| fields interval, challenger_pct'
```

### Latency by model over time

Use a line chart with one line per model. Compare how fast each answers.

```bash
dtctl query 'fetch spans
| filter service.name == "support-model-selection"
| filter gen_ai.operation.name == "chat"
| filter isNull(gen_ai.agent.name)
| makeTimeseries avg_latency = avg(duration), by: {gen_ai.request.model}, interval: 1m'
```

### Output tokens by model over time

Use a line chart. This is your cost signal: fewer output tokens per answer is cheaper.

```bash
dtctl query 'fetch spans
| filter service.name == "support-model-selection"
| filter gen_ai.operation.name == "chat"
| filter isNull(gen_ai.agent.name)
| makeTimeseries avg_output_tokens = avg(gen_ai.usage.output_tokens), by: {gen_ai.request.model}, interval: 1m'
```

### Side-by-side comparison table

Use a table. This produces the numbers for [the report](#the-report).

```bash
dtctl query 'fetch spans
| filter service.name == "support-model-selection"
| filter gen_ai.operation.name == "chat"
| filter isNull(gen_ai.agent.name)
| summarize
    requests = count(),
    avg_input_tokens = round(avg(gen_ai.usage.input_tokens), decimals:0),
    avg_output_tokens = round(avg(gen_ai.usage.output_tokens), decimals:0),
    avg_latency_s = round(avg(toLong(duration)) / 1000000000, decimals:2),
    by: {gen_ai.request.model}'
```

The control row also includes the high-urgency complaints, which never reach the challenger, so its numbers are not a like-for-like comparison. For a fair comparison, filter the control traces to `complaint.urgency <= 2` in the Traces view, as described in [the report](#the-report).

### Verify the split with the routing counter

The same split from the metric rather than the spans. Use this to confirm that the metric and the traces agree.

```bash
dtctl query 'timeseries requests = sum(gen_ai.model_selection.requests), by: {feature_flag.variant}, interval: 30s'
```

### Build the dashboard

Create a new dashboard called **Model migration** with these tiles, in this order, so the story reads from top to bottom:

| Tile | Query | Visualization |
|---|---|---|
| Traffic split over time | Traffic split over time | Stacked area |
| Challenger share (%) | Challenger share (%) over time | Line |
| Latency by model | Latency by model over time | Line |
| Output tokens by model | Output tokens by model over time | Line |
| Comparison | Side-by-side comparison table | Table |

Set the dashboard refresh to 10 seconds and the timeframe to the last 30 minutes before you start the run. Then run `python app-instrumented.py`, and save each `flags.json` edit at its checkpoint. The first tile makes the shift visible to anyone watching.

## The report

At the end of the run, you have the data to make the call. The comparison in Dynatrace looks something like this:

| Metric | Control | Challenger |
|---|---|---|
| Avg input tokens | 312 | 308 |
| Avg output tokens | 187 | 152 |
| Avg latency | 2.4s | 1.1s |
| Requests | 78 | 22 |

The challenger uses fewer output tokens (cheaper) and responds faster. The question is whether the shorter output means the quality is worse. That judgment comes from reading the `gen_ai.output.messages` content in the traces alongside the numbers. Dynatrace gives you both in the same place.

The control group also includes the 40 higher-urgency complaints, which never reach the challenger. To compare fairly, filter the control traces to `complaint.urgency <= 2` first, so both columns cover the same kind of complaint.

This is the report you take to the meeting: cost, latency, and response quality, drawn from real production traffic.

## Summary

| | What's new |
|---|---|
| **Step 1–7** | Observability on a fixed model — single calls, guardrails, pipelines, loops, streaming, and RAG |
| **Step 8** | Feature-flag-controlled model routing + comparison metrics |

The instrumentation pattern is the same as all previous steps. What changes is that `gen_ai.request.model` now varies across traces, and `feature_flag.*` attributes tell you why. Everything else carries forward unchanged: spans, histograms, OTel semantic conventions.

<div id="dt-quiz-anchor"></div>

## What's next?

That's the last step in the Monitor Production track. Head back to the [Monitor Production AI](index.md) overview.
