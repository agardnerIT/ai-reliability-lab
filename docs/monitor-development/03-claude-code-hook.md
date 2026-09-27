# Step 3: Harness Hooks and Events

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="../01-invisible-cost/" class="dt-trail-step inactive">Step 1: Invisible Cost</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../02-first-dev-span/" class="dt-trail-step inactive">Step 2: Bedrock Telemetry</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 3: Harness Hooks</span>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../04-team-proxy/" class="dt-trail-step inactive">Step 4: Enterprise Push</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../05-cost-attribution/" class="dt-trail-step inactive">Step 5: AI Gateway</a>
  </div>
</div>

Most AI coding harnesses expose a side-channel mechanism that fires on agent actions without requiring you to modify the harness itself. The terminology differs: Claude Code calls them **hooks**, Pi calls them **events** via its extension API. The concept is the same: register an external script, and the harness invokes it when something happens, passing structured data about what just occurred.

This page uses Claude Code as the worked example because it's the most widely deployed harness with a hook system that maps directly to the OTel primitives from Step 2. If you're using Pi, the event payload schema differs but the instrumentation pattern is identical. Read structured JSON, emit a counter, exit.

## What hooks are

Every time Claude Code uses a tool (reading a file, running a bash command, editing code), it invokes any scripts you've registered for that event type, passing a JSON payload via stdin. Your script reads that payload, does whatever it wants with it, and exits.

The [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks) documents the full hook system, including a lifecycle diagram that shows when each event fires within a session.

### All available hook events

**Once per session**

| Event | When it fires |
|-------|--------------|
| `SessionStart` | When a Claude Code session begins |
| `SessionEnd` | When a session ends |

**Once per turn**

| Event | When it fires |
|-------|--------------|
| `UserPromptSubmit` | When the user submits a prompt |
| `UserPromptExpansion` | When a slash command is expanded |
| `Stop` | When Claude finishes a turn successfully |
| `StopFailure` | When a turn ends with an error |
| `TeammateIdle` | When Claude is waiting for input |
| `PreCompact` | Before context compaction |
| `PostCompact` | After context compaction |

**On every tool call**

| Event | When it fires |
|-------|--------------|
| `PreToolUse` | Before a tool executes; can block the call |
| `PermissionRequest` | When a tool needs user permission |
| `PostToolUse` | After a tool completes successfully |
| `PostToolUseFailure` | After a tool call fails |
| `PostToolBatch` | After a batch of tool calls completes |
| `SubagentStart` | When a subagent is spawned |
| `SubagentStop` | When a subagent finishes |
| `TaskCreated` | When a background task is created |
| `TaskCompleted` | When a background task finishes |

**Async events**

| Event | When it fires |
|-------|--------------|
| `WorktreeCreate` | When a git worktree is created |
| `WorktreeRemove` | When a git worktree is removed |
| `Notification` | On any Claude Code notification |
| `ConfigChange` | When settings change |

We register hooks for both `PostToolUse` and `PostToolUseFailure`. Tracking only successes gives you an incomplete picture -- the failure rate is often the most actionable signal.

## The hook script

The script reads the event payload, increments a counter with tool name, outcome, and session ID as dimensions, then writes the event back to stdout unchanged so Claude Code continues processing it.

```python title="dev-03-claude-code-hook/hook.py"
import json
import sys

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

resource = Resource.create({"service.name": "claude-code-session"})

meter_provider = MeterProvider(
    resource=resource,
    metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
)
metrics.set_meter_provider(meter_provider)

meter = metrics.get_meter("claude-code-hook", "1.0.0")

tool_calls = meter.create_counter(
    name="claude_code.tool.calls",
    unit="{call}",
    description="Claude Code tool invocations, split by tool name and outcome",
)

# Passed by the hook registration: "success" (PostToolUse) or "failure" (PostToolUseFailure)
status = sys.argv[1] if len(sys.argv) > 1 else "success"

event = json.load(sys.stdin)

tool_name  = event.get("tool_name", "unknown")
session_id = event.get("session_id", "unknown")

tool_calls.add(1, {
    "tool.name":   tool_name,
    "tool.status": status,
    "session.id":  session_id,
    "dev.tool":    "claude-code",
})

# force_flush rather than shutdown — hooks are short-lived processes.
meter_provider.force_flush()

json.dump(event, sys.stdout)
sys.exit(0)
```

Use `force_flush()` rather than `shutdown()`. Hooks are short-lived processes. `force_flush()` sends buffered data and returns; `shutdown()` does the same but also disables the provider, which is unnecessary for a script that exits immediately after.

## Registering the hook

Register the same script for both event types, passing the outcome as a command argument.

```json title="dev-03-claude-code-hook/settings.json"
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/dev-03-claude-code-hook/hook.py success"
          }
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/dev-03-claude-code-hook/hook.py failure"
          }
        ]
      }
    ]
  }
}
```

The `matcher` field is a regex matched against the tool name. `.*` matches all tools. Place this in `~/.claude/settings.json` (applies to all projects) or `.claude/settings.json` in a specific project directory.

## Running it

```bash
cd ai-aws-bedrock-1

export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

Register the hook in `settings.json`, then use Claude Code normally. Every tool call emits a `claude_code.tool.calls` counter to Dynatrace with `tool.name`, `tool.status`, `session.id`, and `dev.tool` dimensions.

## Seeding demo data

Davis AI requires at least 14 data points before it can produce a forecast. If you've just set up the hook, you don't have that yet. The seed script injects 20 historical data points directly into Dynatrace via the Metrics Ingest API, spread across the past 20 minutes at 1-minute intervals, so the forecast analyzer is ready to use immediately.

```bash
export DT_ENDPOINT=https://<your-environment>.live.dynatrace.com
export DT_API_TOKEN=<token-with-metrics.ingest-scope>

python dev-03-claude-code-hook/seed-data.py
```

The script generates realistic variation in tool call counts and includes one deliberate spike at minute 15, which gives the forecast something concrete to detect. Wait about a minute after running it for Dynatrace to finish indexing the data before opening the notebook.

## Enabling forecast analysis

Open a Dynatrace Notebook and add a DQL tile querying `claude_code.tool.calls`. Then:

1. Click the **⋮** (options) menu on the tile
2. Select **Analyze and alert**
3. In the analyzer picker, choose **Forecast**
4. Set the metric to `claude_code.tool.calls` and split by `tool.name`
5. Run the analysis

The forecast view shows the expected range for the metric over the next period and flags where the actual values fall outside it. The spike injected by the seed script appears as an anomaly. In production, this is where a genuine runaway session would surface.

## What to look for

### Tool failure rate

Split `claude_code.tool.calls` by `tool.status` and look at the ratio of `failure` to `success` per `tool.name`.

A spike in `Bash` failures usually means a broken shell environment -- a missing binary, a permissions issue, or a path that changed. A spike in `Edit` failures often means Claude is trying to modify a file it doesn't have write access to, or its mental model of the file has drifted from the actual content. Both are actionable: the signal tells you where to look without requiring you to read every session transcript.

A baseline failure rate of zero is also a red flag. It more likely means failures aren't being captured than that nothing is going wrong.

### Runaway sessions

Look at `sum(claude_code.tool.calls)` grouped by `session.id`. Most sessions will cluster around a similar count for a given type of task. A session with ten times the normal call volume is an agent that got stuck in a loop, spinning through the same sequence of tool calls repeatedly without making progress.

Catching this early matters: a stuck agent keeps consuming tokens on every loop iteration. By the time it times out or the developer notices, the cost can be significant.

What counts as "too many" calls depends entirely on your team and your tasks -- there's no universal threshold. The right answer is to let Davis AI learn your baseline.

### Tool mix as a signal of prompt quality

The distribution of `tool.name` values across sessions tells you something about how Claude is spending its time. A session that's 80% `Read` calls is spending most of its time exploring the codebase before acting. That's normal early in a task, but if it's the consistent pattern across sessions, it often means prompts aren't giving Claude enough context to act directly.

Tracking this over time shows you whether prompt improvements are actually changing Claude's behavior.

## Baselining with Davis AI

The problem with static alert thresholds is that "high" is relative. A session making 200 tool calls might be normal for a large refactor and alarming for a quick bug fix. A static threshold of 150 would either miss the genuine anomalies or fire constantly on legitimate work.

Dynatrace's Davis AI builds adaptive baselines for custom metrics automatically. Once `claude_code.tool.calls` is flowing, you can set up a metric event in **Settings > Anomaly detection > Metric events** that alerts when the per-session call rate deviates from its learned baseline. Davis factors in time-of-day and day-of-week patterns, so a spike during a Friday afternoon deployment push isn't treated the same as the same spike at 2am.

### Data requirements

Davis requires a minimum of 14 data points before a baseline can be trained. For seasonal patterns (time-of-day, day-of-week), you need at least 2-7 days of data. If you try to enable baselining before this threshold is met, you'll get an error: `at least 14 values are present in the last third of the time series`.

On day one, use a static threshold as a starting point. Pick a conservative number -- something like three times the average call count you observe in your first few sessions -- and treat it as a temporary guardrail. Once you have a week of data, replace the static threshold with a Davis baseline. At that point Davis has enough history to detect genuine anomalies without false positives from normal task variation.

The baseline adapts as your team's usage grows. You don't update thresholds manually as the team expands or as usage patterns shift -- Davis adjusts automatically.

## A note on deployment

Hooks can be pushed to developer machines via policy. If your organisation manages developer machines with MDM or configuration management tooling, you can deploy `hook.py` and `settings.json` centrally. Individual developers may not know the hook is running.

The recommendation here is simple: tell your developers. The goal of this telemetry is to understand aggregate usage, not to monitor individuals covertly. Developers who know about the telemetry are more likely to trust the data and engage constructively with what it shows.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 4: Team Proxy →](04-team-proxy/)
