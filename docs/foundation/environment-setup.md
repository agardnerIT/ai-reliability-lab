# Environment Setup

Before running any of the tutorial code, you need a working Python environment, a way to reach AWS Bedrock, and a local OTel Collector. This page covers three ways to get there. Pick the one that fits your setup, or ask your instructor if you're not sure which applies.

## What you need either way

Two things are the same no matter which option you pick below:

- **Your own AWS credentials with Bedrock access.** These tutorials use AWS Bedrock Mantle, and you'll need an AWS account with Bedrock enabled. See [AWS Bedrock](aws-bedrock.md) for the prerequisites, and the console's ["Getting started" page for Bedrock Mantle](https://us-east-2.console.aws.amazon.com/bedrock-mantle/projects/default/getting-started) to download your credentials.
- **A Dynatrace API token.** If you're attending a live class, your instructor will walk through generating this together, so there's nothing to prepare in advance. See [Dynatrace Setup](dynatrace-setup.md) for the steps.

## Option 1: GitHub Codespaces (recommended)

This is the fastest way to get hands-on. It runs everything in your browser, so there's nothing to install on your laptop.

1. Open this repository on GitHub.
2. Click **Code → Codespaces → Create codespace on main**.
3. Wait for the codespace to build. This installs Python and all the dependencies for every exercise automatically.
4. A local OTel Collector starts alongside your codespace, already listening on port 4318. See [Adding your Dynatrace token](#adding-your-dynatrace-token) below once you've generated one.

!!! tip "Add your AWS credentials as Codespaces secrets"
    Rather than pasting your AWS keys into a shared terminal during class, set them once as Codespaces secrets: on GitHub, go to **Settings → Codespaces → Secrets**, and add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and (if your credentials include one) `AWS_SESSION_TOKEN`, scoped to this repository. They'll be available automatically as environment variables inside every codespace you create.

!!! warning "Some organisations block Codespaces"
    Codespaces is sometimes disabled by organisational policy, or capped at a size too small to run these exercises. If you can't create a codespace, use Option 2 or Option 3 below instead.

## Option 2: A local dev container

If Codespaces isn't available to you but you already have [Docker Desktop](https://www.docker.com/products/docker-desktop/) and [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers), you can run the exact same setup locally:

1. Clone this repository.
2. Open it in VS Code.
3. Run **Dev Containers: Reopen in Container** from the command palette.
4. Wait for the container to build. As with Codespaces, this installs everything and starts the OTel Collector for you. See [Adding your Dynatrace token](#adding-your-dynatrace-token) below once you've generated one.

For your AWS credentials, the dev container mounts your local `~/.aws` folder automatically, so if you already have `aws configure` set up on your machine, it just works.

## Adding your Dynatrace token

Options 1 and 2 both use the same setup, so this step is identical either way. It's the one thing you can't do until your instructor walks through generating a Dynatrace API token in class, so there's nothing to do here in advance.

1. In the integrated terminal, copy the template: `cp .devcontainer/.env.example .devcontainer/.env`
2. Open `.devcontainer/.env` and fill in `DT_TENANT` and `DT_API_TOKEN` with the values from the walkthrough.
3. Apply the change by recreating the collector container: `docker compose -f .devcontainer/docker-compose.yml up -d otel-collector`

`.devcontainer/.env` is gitignored, so this never gets committed. Until you complete this step, the collector still runs, it just has nowhere to send data yet.

## Option 3: Plain Python, no containers

If your organisation restricts both Codespaces and Docker, you can still run everything with just Python installed locally.

1. Install Python 3.9 or later.
2. Create a virtual environment and install the dependencies for the exercise you're working on:

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

    Each exercise folder has its own `requirements.txt`, so repeat this `pip install` step when you move to a new folder.

3. Run a local OTel Collector. See [Dynatrace Setup](dynatrace-setup.md) for both the Docker and the no-Docker (downloaded binary) versions of this step.

## Which option should I pick?

| | Setup time | Needs on your laptop |
|---|---|---|
| Codespaces | Fastest | A browser and a GitHub account |
| Local dev container | Moderate | Docker Desktop, VS Code |
| Plain Python | Depends on your machine | Python 3.9+, and a way to run (or download) the OTel Collector |

If you're not sure, start with Codespaces. It's the option we'll demonstrate in class.
