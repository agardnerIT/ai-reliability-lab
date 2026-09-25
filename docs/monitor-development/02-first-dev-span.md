# Step 2: AWS Bedrock Telemetry

<div class="dt-trail">
  <div class="dt-trail-item">
    <a href="../01-invisible-cost/" class="dt-trail-step inactive">Step 1: Developer AI Usage</a>
    <span class="dt-trail-arrow">→</span>
  </div>
  <div class="dt-trail-item">
    <span class="dt-trail-step">Step 2: Bedrock Telemetry</span>
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

AWS Bedrock logs every model invocation natively. You can turn this on without writing any code, and Dynatrace's AWS integration can pull the resulting metrics directly from CloudWatch.

This is the lowest-effort option. No instrumentation, no hook scripts, no proxy. You enable a setting in the AWS console and point Dynatrace at your AWS account.

## What Bedrock logs

When model invocation logging is enabled, Bedrock writes a record for every API call to your account: the model used, token counts, latency, and whether the call succeeded. These records go to CloudWatch Logs and, optionally, S3.

CloudWatch also surfaces a set of Bedrock metrics automatically: invocation count, latency percentiles, input and output token counts, and throttling events. These are per-model and per-account, updated in near real time.

## Enabling model invocation logging

In the AWS console, go to **Amazon Bedrock > Configure and Learn > Settings > Model invocation logging**.

Turn on logging and choose your destination. CloudWatch is the easiest starting point: Bedrock creates the log group and writes to it automatically. S3 is better if you want long-term retention or need the raw request and response payloads for audit purposes.

You need one IAM permission for Bedrock to write to CloudWatch:

```json
{
  "Effect": "Allow",
  "Action": [
    "logs:CreateLogGroup",
    "logs:CreateLogStream",
    "logs:PutLogEvents"
  ],
  "Resource": "arn:aws:logs:*:*:log-group:/aws/bedrock/*"
}
```

That is the full setup on the AWS side.

## Pulling metrics into Dynatrace

Dynatrace's AWS integration polls CloudWatch metrics on a configurable interval. Once your AWS account is connected, go to **Settings > Cloud and virtualisation > AWS**, select your account, and enable the following services:

- **Amazon Bedrock Agents**
- **Amazon Bedrock Guardrails**

Once enabled, check **Metrics** and search for `aws.bedrock`. You should see:

| Metric | What it shows |
|--------|--------------|
| `aws.bedrock.invocations` | Total model calls, per model |
| `aws.bedrock.invocationlatency` | Latency percentiles per model |
| `aws.bedrock.inputtokencount` | Input tokens consumed per model |
| `aws.bedrock.outputtokencount` | Output tokens generated per model |
| `aws.bedrock.invocationthrottles` | Throttled requests per model |

Split any of these by the `ModelId` dimension to see the breakdown per model across your account.

## What this gives you and what it doesn't

Bedrock telemetry is account-level. You can see that your account made 4,000 Claude Sonnet calls yesterday and consumed 12 million input tokens. You cannot see which developer or tool generated those calls, because that information is not in the Bedrock logs.

If all you need is aggregate visibility across your AWS account, this is enough. If you need per-developer attribution or per-tool breakdown, you need one of the approaches in Steps 3 to 5.

???+ info "Bedrock Mantle and invocation logging"
    If your organisation uses Bedrock Mantle (the OpenAI-compatible endpoint), check whether invocation logging applies at the Mantle layer or the underlying Bedrock layer. Logging behaviour may differ depending on how Mantle is configured in your account.

<div id="dt-quiz-anchor"></div>

## Next step

[Step 3: Harness Hooks →](03-claude-code-hook.md)
