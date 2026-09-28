# Environment Setup

Before running any of the tutorial code, you need a working Python environment, a way to reach AWS Bedrock, and a local OTel Collector. These tutorials run inside a GitHub Codespace — everything is pre-configured for you.

## What you need

Two things are required before you start:

- **Your own AWS credentials with Bedrock access.** These tutorials use AWS Bedrock Mantle, and you'll need an AWS account with Bedrock enabled. See [AWS Bedrock](aws-bedrock.md) for the prerequisites, and the console's ["Getting started" page for Bedrock Mantle](https://us-east-2.console.aws.amazon.com/bedrock-mantle/projects/default/getting-started) to download your credentials.
- **A Dynatrace API token.** If you're attending a live class, your instructor will walk through generating this together, so there's nothing to prepare in advance. See [Dynatrace Setup](dynatrace-setup.md) for the steps.

## GitHub Codespaces

This is how these tutorials are run. Everything executes in your browser — there's nothing to install on your laptop.

1. Open this repository on GitHub.
2. Click **Code → Codespaces → Create codespace on main**.
3. Wait for the codespace to build. This installs Python and all the dependencies for every exercise automatically.
4. A local OTel Collector starts alongside your codespace, already listening on port 4318. See [Adding your Dynatrace token](#adding-your-dynatrace-token) below once you've generated one.

!!! tip "Add your AWS credentials as Codespaces secrets"
    Rather than pasting your AWS keys into a shared terminal during class, set them once as Codespaces secrets: on GitHub, go to **Settings → Codespaces → Secrets**, and add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and (if your credentials include one) `AWS_SESSION_TOKEN`, scoped to this repository. They'll be available automatically as environment variables inside every codespace you create.

## Adding your Dynatrace token

This is the one thing you can't do until your instructor walks through generating a Dynatrace API token in class, so there's nothing to do here in advance.

1. In the integrated terminal, copy the template: `cp .devcontainer/.env.example .devcontainer/.env`
2. Open `.devcontainer/.env` and fill in `DT_TENANT` and `DT_API_TOKEN` with the values from the walkthrough.
3. Apply the change by recreating the collector container: `docker compose -f .devcontainer/docker-compose.yml up -d otel-collector`

`.devcontainer/.env` is gitignored, so this never gets committed. Until you complete this step, the collector still runs, it just has nowhere to send data yet.

