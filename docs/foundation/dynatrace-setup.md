# Dynatrace Setup

Before you can run the instrumented examples and see data in Dynatrace, you need two things:

1. Your **Environment URL** (where your Dynatrace instance lives)
2. An **API token** (so the OTel Collector can send data to it)

## Finding your Environment URL

Your Dynatrace environment URL looks like one of these:

```
https://abc12345.live.dynatrace.com   # SaaS (classic)
https://abc12345.apps.dynatrace.com   # SaaS (platform)
```

You can find it in your browser's address bar when logged into Dynatrace.

The important part is the **tenant ID** — the `abc12345` part. This is what you put in `DT_TENANT`.

## Creating an API Token

The OTel Collector needs an API token with permission to ingest spans and metrics.

**Steps:**

1. In Dynatrace, press `Ctrl / Cmd + k` and search for `Access tokens`
2. Click **Generate new token**
3. Give it a name, e.g. `otel-collector-local`
4. Add these two scopes:
    - `openTelemetryTrace.ingest` (to send traces/spans)
    - `metrics.ingest` (to send metrics)
5. Click **Generate token**
6. **Copy the token immediately.** You won't be able to see it again.

!!! warning "Token security"
    Treat this token like a password. Don't commit it to git. Use environment variables or a secrets manager.

## Creating a platform token

The `dtctl` CLI uses a **platform token** (`dt0s16.` prefix) to run DQL queries. This is separate from the OTel Collector token above.

**Steps:**

1. Go to `https://myaccount.dynatrace.com/platformTokens`
1. In Dynatrace, go to **Account Management → Platform tokens** (or press `Ctrl / Cmd + k` and search for `Platform tokens`)
2. Click **Generate token**
3. Give it a name, e.g. `dtctl-local`
4. Add these three scopes:
    - `storage:metrics:read`
    - `storage:spans:read`
    - `storage:buckets:read`
5. Click **Generate** and **copy the token immediately.**

!!! warning "Token security"
    Same rule as above — never commit this token.

## Setting your credentials

### Devcontainer or Codespaces (Options 1 and 2)

If you're running in a Codespace or local dev container, **the OTel Collector is already running**. You do not need to start one yourself.

All you need to do is give it your Dynatrace credentials:

1. In the integrated terminal, copy the template:

    ```bash
    cp .devcontainer/.env.example .devcontainer/.env
    ```

2. Open `.devcontainer/.env` and fill in the three values:

    ```
    # OTel Collector
    DT_TENANT=abc12345
    DT_API_TOKEN=dt0c01.XXXX...

    # dtctl (DQL queries) — URL is derived from DT_TENANT automatically
    DTCTL_PLATFORM_TOKEN=dt0s16.XXXX...
    ```

    `DT_TENANT` / `DT_API_TOKEN` are used by the OTel Collector. `DTCTL_PLATFORM_TOKEN` is a separate token used by `dtctl` for DQL queries — see [Creating a platform token](#creating-a-platform-token) below.

3. (from host machine) Restart the collector so it picks up the new values:

    ```bash
    docker compose -f .devcontainer/docker-compose.yml up -d otel-collector
    ```

4. Register the dtctl context (run once inside the devcontainer terminal):

    ```bash
    source .devcontainer/.env

    dtctl config set-context lab \
      --environment "https://${DT_TENANT}.apps.dynatrace.com" \
      --token-ref lab-token

    dtctl config set-credentials lab-token --token "$DTCTL_PLATFORM_TOKEN"
    ```

    The `source` line loads your credentials into the current shell so the `$` variables expand correctly. You only need to do this once per container. Re-run it if you rebuild the container or change your token.

`.devcontainer/.env` is gitignored, so your tokens are never committed. Until you complete this step the collector still runs, it just has nowhere to send data (it outputs to the debug console only).

### Plain Python, no containers (Option 3)

If you're not using a devcontainer, you need to run a local OTel Collector yourself.

#### Collector config

Create a file called `otel-collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  otlp_http/dynatrace:
    endpoint: "https://${DT_TENANT}.live.dynatrace.com/api/v2/otlp"
    headers:
      Authorization: "Api-Token ${DT_API_TOKEN}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp_http/dynatrace]
    metrics:
      receivers: [otlp]
      exporters: [otlp_http/dynatrace]
```

The collector reads `DT_TENANT` and `DT_API_TOKEN` from its environment at startup, so your credentials never live in the config file.

#### Run it with Docker

```bash
docker run \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  -e DT_TENANT=abc12345 \
  -e DT_API_TOKEN=dt0c01.XXXX... \
  -p 4318:4318 \
  otel/opentelemetry-collector-contrib:latest
```

Once the collector is running, your instrumented apps can send data to `http://localhost:4318`.

Port **4318** is the OTLP/HTTP port. The other common OTel port, 4317, is for gRPC. The examples in this tutorial use HTTP, which is simpler to configure and works everywhere without extra dependencies.

???+ tip "No Docker?"
    You can also download a pre-built binary from the [Dynatrace OTel Collector releases page](https://github.com/Dynatrace/dynatrace-otel-collector/releases). This is Dynatrace's own distribution, pre-configured with the exporters you need.

## Verify the plumbing works

**Do this immediately after restarting the collector.** Every exercise in the lab depends on this pipeline. Catching a misconfiguration now saves a lot of confusion later.

### Run the smoke test

```bash
python code/smoke-test.py
```

Expected output:

```
Sending to: http://localhost:4318
Span recorded:  smoke-test
Metric recorded: smoke_test.runs +1
Done. Wait ~60 s then verify with:
  Spans:   dtctl query 'fetch spans | filter service.name == "otel-smoke-test" | limit 5'
  Metrics: dtctl query 'timeseries sum(smoke_test.runs), by:{service.name} | filter service.name == "otel-smoke-test"'
```

If the script exits with a connection error, the collector is not reachable on port 4318. Re-check the restart step above.

### Confirm data arrived in Dynatrace

Wait about **60 seconds** after the script finishes, then run the two queries below from the integrated terminal using the `dt` CLI (pre-installed in the devcontainer).

#### Trace check

```bash
dtctl query 'fetch spans
| filter service.name == "otel-smoke-test"
| fields timestamp, span.name, duration
| sort timestamp desc
| limit 5'
```

You should see at least one row with `span.name = smoke-test`. If the result is empty, the collector did not forward spans — double-check your `DT_API_TOKEN` has the `openTelemetryTrace.ingest` scope.

#### Metric check

```bash
dtctl query 'timeseries runs = sum(smoke_test.runs), by: {service.name}
| filter service.name == "otel-smoke-test"'
```

You should see a result like this:

```
INTERVAL      RUNS          SERVICE NAME      TIMEFRAME
60000000000   <121 items>   otel-smoke-test   <2 items>
```

!!! success "Both queries return data?"
    Your end-to-end pipeline is confirmed. Move on to the next section.

!!! failure "One or both queries return nothing?"
    1. Confirm the OTel Collector token scopes: `openTelemetryTrace.ingest` and `metrics.ingest`.
    2. Check the collector logs: `docker logs $(docker ps -q --filter "name=otel-collector") | tail -30`
    3. Look for lines containing `error` or `REFUSED` — these usually name the missing permission.
