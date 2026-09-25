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

The important part is the **Environment ID**, the `abc12345` part. You'll need this for the collector config.

## Creating an API Token

The OTel Collector needs an API token with permission to ingest spans and metrics.

**Steps:**

1. In Dynatrace, go to **Settings → Access tokens** (or search for "Access tokens")
2. Click **Generate new token**
3. Give it a name, e.g. `otel-collector-local`
4. Add these two scopes:
    - `openTelemetryTrace.ingest` (to send traces/spans)
    - `metrics.ingest` (to send metrics)
5. Click **Generate token**
6. **Copy the token immediately.** You won't be able to see it again.

!!! warning "Token security"
    Treat this token like a password. Don't commit it to git. Use environment variables or a secrets manager.

## Setting up the OTel Collector

The easiest way to run a collector locally is with Docker.

### Collector config

Create a file called `otel-collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

exporters:
  otlphttp/dynatrace:
    endpoint: "https://${env:DT_ENV_ID}.live.dynatrace.com/api/v2/otlp"
    headers:
      Authorization: "Api-Token ${env:DT_API_TOKEN}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/dynatrace]
    metrics:
      receivers: [otlp]
      exporters: [otlphttp/dynatrace]
```

The collector reads `DT_ENV_ID` and `DT_API_TOKEN` from its environment at startup, so your credentials never live in the config file.

### Run it with Docker

```bash
docker run \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml \
  -e DT_ENV_ID=abc12345 \
  -e DT_API_TOKEN=dt0c01.XXXX... \
  -p 4318:4318 \
  otel/opentelemetry-collector-contrib:latest
```

Once the collector is running, your instrumented apps can send data to `http://localhost:4318`.

Port **4318** is the OTLP/HTTP port. The other common OTel port, 4317, is for gRPC. The examples in this tutorial use HTTP, which is simpler to configure and works everywhere without extra dependencies.

???+ tip "No Docker?"
    You can also download a pre-built binary from the [Dynatrace OTel Collector releases page](https://github.com/Dynatrace/dynatrace-otel-collector/releases). This is Dynatrace's own distribution, pre-configured with the exporters you need.
