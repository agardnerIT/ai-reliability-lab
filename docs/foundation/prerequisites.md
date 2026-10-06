# Prerequisites

Confirm every item below **before the lab starts**. Several items (AWS access, Dynatrace tokens) can take time to arrange, so check them early.

## Checklist

### On your machine

- [ ] **A GitHub account**, so you can fork this repository. You don't have write access to the source repository.
- [ ] **A container runtime with `docker` and `docker compose`**, installed and running. The dev container needs both commands. Verify with `docker run hello-world` and `docker compose version`. See [Container runtime](#container-runtime) below.
- [ ] **[VS Code](https://code.visualstudio.com/)** with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).
- [ ] **Git** installed. Verify with `git --version`.
- [ ] **Free port `4318`** on localhost. The OpenTelemetry Collector listens here.

!!! note "Nothing else to install"
    Python, the OpenTelemetry Collector and the `dtctl` CLI all run inside the dev container. You don't need to install them on your host.

### AWS

- [ ] **An AWS account or identity** that can use Amazon Bedrock in `us-east-2`.
- [ ] **IAM permissions** to invoke Bedrock models and guardrails. The exact policy is in [Setup, Step 1](setup.md#required-iam-permissions).
- [ ] **Working AWS credentials in `~/.aws`**, set up by one of the two paths in [AWS credentials](#aws-credentials) below.
- [ ] **Permission to create a Bedrock Guardrail**, or an existing guardrail ID. Step 3 of the lab needs one.

### Dynatrace

- [ ] **A Dynatrace environment** you can sign in to. Note your tenant ID (the `abc12345` in `https://abc12345.live.dynatrace.com`).
- [ ] **Permission to create an access token** with the `openTelemetryTrace.ingest` and `metrics.ingest` scopes.
- [ ] **Permission to create a platform token** with the `storage:metrics:read`, `storage:spans:read` and `storage:buckets:read` scopes.

## Container runtime

The lab runs in two containers started with Docker Compose, so you need a runtime that provides both `docker` and `docker compose`.

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** is the simplest option, but it requires a paid licence for many organisations.
- **[Rancher Desktop](https://rancherdesktop.io/)** is a free alternative. In its settings, choose the **dockerd (moby)** container engine, not containerd. The dev container uses the `docker` and `docker compose` commands, which only the dockerd engine provides.
- Any other runtime works if it provides working `docker` and `docker compose` commands (for example Colima, or Docker Engine on Linux).

Whichever you choose, make sure it is running before you open the dev container.

## AWS credentials

The dev container mounts your `~/.aws` folder, so the lab uses whatever credentials are in there. **The folder must exist or the container won't start.** Pick the path that matches you.

### Path 1: You already have the AWS CLI and it works

You're done. Check it with:

```bash
aws sts get-caller-identity
```

If that prints your account and identity, the container will pick up the same credentials.

- **SSO users:** run `aws sso login --profile your-profile-name` on your host before starting the lab, and again whenever the session expires.
- **Non-default profile:** if your profile isn't called `default`, add `AWS_PROFILE=your-profile-name` to `.devcontainer/.env`.
- Make sure the identity has the [IAM permissions](setup.md#required-iam-permissions) the lab needs.

### Path 2: You don't have the AWS CLI

You don't need to install it. You need an access key and a credentials file.

1. **Create an IAM user and access key.** Follow [Setup, Option B](setup.md#option-b-iam-user-with-access-keys). You end up with an `AWS_ACCESS_KEY_ID` (starts with `AKIA`) and an `AWS_SECRET_ACCESS_KEY`.
2. **Create the folder and file on your machine:**

    ```bash
    mkdir -p ~/.aws
    touch ~/.aws/credentials
    ```

3. **Put your keys in `~/.aws/credentials`.** Replace the placeholders:

    ```ini
    [default]
    aws_access_key_id = AKIAXXXXXXXXXXXXXXXX
    aws_secret_access_key = REPLACE_WITH_YOUR_SECRET_KEY
    ```

    If you were given temporary credentials (they come with a session token), add one more line:

    ```ini
    aws_session_token = REPLACE_WITH_YOUR_SESSION_TOKEN
    ```

    You don't need a `config` file. The region (`us-east-2`) is set by the dev container.

**Prefer not to create a credentials file?** Run `mkdir -p ~/.aws` to create the empty folder, then put `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and (for temporary credentials) `AWS_SESSION_TOKEN` in `.devcontainer/.env`. See [Setup, Step 2.3](setup.md#step-2-start-the-dev-container).

!!! warning "Keep keys out of git"
    `~/.aws/credentials` lives outside the repository, so it can't be committed by accident. Never paste keys into files inside the repository other than the gitignored `.devcontainer/.env`.

## Check your readiness

Before you start, confirm that you can answer "yes" to each of these:

| Question | If no |
|---|---|
| Do `docker run hello-world` and `docker compose version` both succeed? | Start your container runtime, or install one that provides `docker` and `docker compose`. |
| Can you open the AWS Console and find **Amazon Bedrock**? | Ask your AWS administrator for access. |
| Is `us-east-2` available to you for Bedrock? | Ask your AWS administrator to enable it. |
| Can you open **Access tokens** in Dynatrace (`Ctrl / Cmd + k`)? | Ask your Dynatrace administrator for token permissions. |

## Security reminders

- Never commit credentials, tokens or `.devcontainer/.env` to git.
- If you use IAM access keys, delete the user and keys when the lab is over.

## Next step

Once everything above is ticked, continue to **[Setup](setup.md)**.
