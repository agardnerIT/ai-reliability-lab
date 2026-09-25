# Step 1: Developer AI Usage

<div class="dt-trail">
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 1: Invisible Cost</span>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../02-first-dev-span/" class="dt-trail-step inactive">Step 2: Bedrock Telemetry</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <a href="../03-claude-code-hook/" class="dt-trail-step inactive">Step 3: Harness Hooks</a>
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

You're not writing AI code anymore. You're using AI tools to write code for you.

Claude Code, Cursor, GitHub Copilot, Windsurf are all harnesses. You open your editor, describe what you need, and the harness handles everything: constructing the prompt, injecting context (open files, git history, terminal output), calling the model, and streaming the response back. You see the result. You don't see the request, the token count, or what it cost.

Every one of those interactions is a model call with a cost, a latency, and a model choice. Across a team of thirty developers running sessions all day, that's hundreds or thousands of calls. Almost none of it is measured.

## What you don't control

You choose the model. What you don't control is how many calls the harness makes or what it sends in each one.

A single prompt to Claude Code can trigger several model calls: one to decide which tools to use, others to read files, run commands, and generate code. Each is a separate request with its own token count. You see one interaction. Multiple billing events happened.

Context injection compounds this. Claude Code reads your open files, your recent git commits, your shell history, and includes whatever it judges relevant. Your prompt might be twenty words. The actual request sent to the model might be twenty thousand tokens, depending on what the harness decided to include.

You have no visibility into how many calls were made, what was sent in each one, or what any of it cost.

## Why this compounds at team scale

You using Claude Code heavily for a day is a rounding error. Thirty developers doing the same for a month is a budget line item that someone will eventually notice and react to.

Without visibility, organisations respond to surprise AI spend with blunt instruments: disable the tool, cap everyone, add approval gates. Those measures don't require any information about what actually happened, so they hit everyone equally, including developers who were using the tools responsibly.

If one person's sessions account for a disproportionate share of spend, that's a specific conversation. Everyone else keeps working. If a harness is defaulting to an expensive model for tasks a cheaper one would handle, that's a configuration change, not a policy change.

Neither conversation can happen without data, and right now none of this is being captured.

## What we fix across these steps

The rest of this path works through the observability options in order of effort, from pulling existing AWS telemetry through to running a proxy that sees every AI call across your whole team.

None of these approaches require you to change how you work or instrument any code. The goal is visibility into harness usage, not adding OTel to generated code.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 2: AWS Bedrock Telemetry →](02-first-dev-span.md)
