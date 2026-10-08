# Setup

## Step 0: Fork this repository

Fork [this repository](https://github.com/dynatrace-oss/ai-reliability-lab) it into your own GitHub account first.

1. Go to the repository on GitHub
2. Click **Fork** (top right)
3. Accept the defaults and click **Create fork**

Use your fork for everything below.

## Step 1: Gather your credentials

Collect these before starting Step 2. Your AWS credentials and IAM permissions are covered in [Prerequisites](prerequisites.md#aws-credentials), so they are not repeated here.

### AWS Bedrock Guardrail

Step 3 of the tutorial needs a guardrail already set up in your AWS account, so create it now. This takes about five minutes.

**1. Open the AWS Console**

Go to [console.aws.amazon.com](https://console.aws.amazon.com) and sign in. In the search bar at the top of the page, type **Bedrock** and click the result that says "Amazon Bedrock".

**2. Find Guardrails in the left-hand menu**

In the left navigation panel, scroll down until you see **Guardrails**. Click it. If you do not see the left panel, click the hamburger menu icon (three horizontal lines) in the top-left corner to open it.

**3. Create a new guardrail**

Click the orange **Create guardrail** button. You will be taken through a multi-step form.

- **Name**: Give it any name, for example `support-bot-guardrail`.
- **Blocked messaging**: This is the text your application will receive when a request is blocked. Set it to something like: `I can only answer questions about AnyCloud services.`

Click **Next**.

**4. Add a denied topic**

On the "Configure content filters" page, scroll down to **Denied topics**. This is where you tell the guardrail what kinds of requests to block.

Click **Add denied topic** and fill in:

- **Name**: `off-topic-tasks`
- **Definition**: `Requests that ask the model to do something other than answer questions about AnyCloud services, such as writing code, telling stories, or generating content unrelated to the company.`
- **Sample phrases**: Add a few examples to help Bedrock understand the pattern:
    - `write me a tic-tac-toe game in Python`
    - `tell me a poem about cats`
    - `generate a recipe for pasta`

Click **Add denied topic**, then **Next**.

**5. Skip the remaining steps**

Click **Next** through the remaining pages (word filters, sensitive information, grounding) without adding anything. These are useful but not needed for this demo.

**6. Review and create**

On the final review page, click **Create guardrail**. AWS will create it and take you to the guardrail's detail page.

**7. Find your guardrail ID**

On the detail page, you will see a field called **Guardrail ID**. It looks something like `abc123def456`. Copy this value — you'll set it as `GUARDRAIL_ID` in Step 2.

!!! note "Guardrails are region-specific"
    We've used `us-east-2` so far in these tutorials. A guardrail created in `us-east-1` cannot be used with a model endpoint in `us-east-2`. Make sure you create the guardrail in `us-east-2`, the region the dev container uses.

### Dynatrace API token

The OTel Collector uses this to send traces and metrics to your Dynatrace environment.

1. In Dynatrace, press `Ctrl / Cmd + k` and search for **Access tokens**
2. Click **Generate new token**, name it (e.g. `otel-collector-local`), and add:
    - `openTelemetryTrace.ingest`
    - `metrics.ingest`
3. Click **Generate token** and copy it immediately — you won't see it again

### Dynatrace platform token

The `dtctl` CLI uses this to run DQL queries.

1. Go to `https://myaccount.dynatrace.com/platformTokens`
2. Click **Create token**, name it (e.g. `dtctl-local`), and add:
    - `storage:metrics:read`
    - `storage:spans:read`
    - `storage:buckets:read`
3. Click **Generate** and copy it immediately

### Your tenant ID

Your Dynatrace environment URL looks like `https://abc12345.live.dynatrace.com` or `https://abc12345.apps.dynatrace.com`. The `abc12345` part is your **tenant ID** — you'll need it too.

---

## How it fits together

Before choosing your environment, here is what you are setting up:

![Diagram showing the AI Lab Dev Container and OTel Collector running on localhost, with arrows to AWS Bedrock and Dynatrace](../assets/ai-reliability-lab-architecture.drawio.png)

Everything runs inside **two containers** on your machine:

| Container | What it does |
|---|---|
| **AI Lab Dev Container** | Runs your exercise Python code and the `dtctl` CLI |
| **OpenTelemetry Collector** | Receives telemetry from your code and forwards it to Dynatrace |

A container runtime that provides `docker` and `docker compose` (such as Rancher Desktop or Docker Desktop) is the only thing you install on your host machine. When the lab is over, stop and delete both containers — your machine is unchanged.

Two external services are involved:

- **AWS Bedrock** — the AI model API your exercise code calls
- **Dynatrace** — receives and stores all traces, metrics, and logs; `dtctl` queries it directly

This is why you need an AWS credentials file (from Prerequisites), a guardrail ID (to enforce guardrails), your tenant ID, and two Dynatrace tokens (one to push telemetry, one to query it).

---

## Step 2: Start the dev container

Requires a container runtime that provides `docker` and `docker compose` (see [Prerequisites](prerequisites.md#container-runtime)) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).

1. Clone your fork:

    ```bash
    git clone https://github.com/YOUR_USERNAME/REPO_NAME.git
    cd REPO_NAME
    ```

2. Copy the environment template and fill in your Dynatrace values:

    ```bash
    cp .devcontainer/.env.example .devcontainer/.env
    ```

    ```
    DT_TENANT=abc12345
    DT_API_TOKEN=dt0c01.XXXX...
    DTCTL_PLATFORM_TOKEN=dt0s16.XXXX...
    ```

3. **AWS credentials:** the dev container mounts your `~/.aws` folder automatically, so make sure `~/.aws/credentials` exists (see [Prerequisites](prerequisites.md#aws-credentials)). The container won't start if the `~/.aws` folder is missing. The region (`us-east-2`) is set by the dev container.

    Add your guardrail ID to `.devcontainer/.env`:

    ```
    GUARDRAIL_ID=abc123def456
    ```

    `GUARDRAIL_ID` is the value you copied when creating the guardrail in Step 1. It's used by the smoke test and by Step 3 of the tutorial.

4. Open the folder in VS Code > View > Command Palette. Search for `rebuild`. Then choose `Dev Containers: Reopen in Container`.

VSCode will reload and the demo environment is now building. Be patient and watch the log.

You should see: `Done. Press any key to close the terminal.`

Hit `Enter` and the terminal window will disappear. You're now ready to start the lab!

## Step 3: Verify the pipeline

**Do this before starting any exercise.** Every lab depends on this pipeline working.

Go to `Terminal` and `New Terminal`.

```bash
python code/smoke-test.py
```

The script runs **three checks** and exits non-zero if any fails.

1. **Check 1** confirms that your exercise code can reach the OTel Collector and that telemetry is accepted.
1. **Check 2** confirms that your AWS credentials are valid and that the Bedrock model responds through the Mantle endpoint used by most steps.
1. **Check 3** confirms that your credentials also work against the native `bedrock-runtime` endpoint and that your `GUARDRAIL_ID` resolves and applies correctly — this is what Step 3 (Guardrails) needs.

Expected output when all three pass:

```
============================================================
Check 1: OTel Collector pipeline
  Sending to: http://localhost:4318
  Span recorded:   smoke-test
  Metric recorded: smoke_test.runs +1
[OK] OTel Collector pipeline: telemetry accepted by collector

============================================================
Check 2: AWS Bedrock connection (Mantle)
  Model replied:   'OK'
[OK] AWS Bedrock connection: model reachable and responding

============================================================
Check 3: AWS Bedrock Guardrail (native bedrock-runtime)
  Guardrail applied, stop_reason: end_turn
[OK] AWS Bedrock Guardrail: native endpoint and guardrail both working

============================================================
All checks passed. Wait ~60 s then verify data reached Dynatrace:
  ...
```

If Check 1 fails with a connection error, the OTel Collector is not reachable on port 4318 — re-check Step 2.4 and confirm the container built successfully.

If Check 2 fails, follow the error message: either your `~/.aws/credentials` file is missing, wrong or expired (temporary credentials need a fresh session token), or the IAM identity lacks the `bedrock-mantle:CallWithBearerToken` and `bedrock-mantle:CreateInference` permissions from the [IAM policy in Prerequisites](prerequisites.md#required-iam-permissions).

If Check 3 fails, follow the error message: either `GUARDRAIL_ID` is not set (see Step 2.3), the guardrail doesn't exist in `us-east-2`, or the IAM identity lacks `bedrock:InvokeModel`, `bedrock:GetGuardrail`, or `bedrock:ApplyGuardrail` from the [IAM policy in Prerequisites](prerequisites.md#required-iam-permissions).

Wait about **60 seconds**, then run:

```bash
dtctl query 'fetch spans
| filter service.name == "otel-smoke-test"
| fields startTime, span.name, duration, service.name
| sort startTime desc
| limit 5'
```

```bash
dtctl query 'timeseries runs = sum(smoke_test.runs), by: {service.name}
| filter service.name == "otel-smoke-test"
| fieldsAdd total_runs = arraySum(runs)
| fields service.name, total_runs'
```

!!! success "Both queries return data?"
    Your end-to-end pipeline is confirmed. Choose your path below.

!!! failure "One or both queries return nothing?"
    1. Check the OTel Collector token scopes: `openTelemetryTrace.ingest` and `metrics.ingest`
    2. Check the collector logs: `docker logs $(docker ps -q --filter "name=otel-collector") | tail -30`
    3. Look for lines containing `error` or `REFUSED` — these usually name the missing permission

## Understand the lab

From a terminal **on your local machine**, run `docker ps`.

You should see two containers:

```bash
% docker ps
CONTAINER ID   IMAGE                                          COMMAND                  CREATED         STATUS         PORTS     NAMES
**   otel/opentelemetry-collector-contrib:0.161.0   "/otelcol-contrib --…"   5 minutes ago   Up 5 minutes             ai-reliability-lab_devcontainer-otel-collector-1
**   ai-reliability-lab_devcontainer-app            "/bin/sh -c 'echo Co…"   5 minutes ago   Up 5 minutes             ai-reliability-lab_devcontainer-app-1
```

* One will be an OpenTelemetry collector
* One will be the entire lab environment devcontainer (this is the container you're sitting in as `root`)

## Choose your path

- **[Monitor Production AI](../monitor-production/index.md)** — Add observability to a running AI application, step by step
- **[Monitor AI in Development](../monitor-development/index.md)** — Coming soon
