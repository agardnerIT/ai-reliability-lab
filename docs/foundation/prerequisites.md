# Prerequisites

Confirm every item below **before the lab starts**. Several items (AWS access, Dynatrace tokens) can take time to arrange, so check them early.

## Checklist

### On your machine

- [ ] **A GitHub account**, so you can fork [this repository](https://github.com/dynatrace-oss/ai-reliability-lab).
- [ ] **A container runtime with `docker` and `docker compose`**, installed and running. The dev container needs both commands. Verify with `docker run hello-world` and `docker compose version`. See [Container runtime](#container-runtime) below.
- [ ] **[VS Code](https://code.visualstudio.com/)** with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).
- [ ] **Git** installed. Verify with `git --version`.
- [ ] **Free port `4318`** on localhost. The OpenTelemetry Collector listens here.

!!! note "Nothing else to install"
    Python, the OpenTelemetry Collector and the `dtctl` CLI all run inside the dev container. You don't need to install them on your host.

### AWS

- [ ] **An AWS account or identity** that can use Amazon Bedrock in `us-east-2`.
- [ ] **IAM permissions** to invoke Bedrock models and guardrails. The exact policy is in [Required IAM permissions](#required-iam-permissions) below.
- [ ] **A `~/.aws/credentials` file** with working credentials. See [AWS credentials](#aws-credentials) below.
- [ ] **Permission to create a Bedrock Guardrail**, or an existing guardrail ID. Step 3 of the lab needs one.

### Dynatrace

- [ ] **A Dynatrace environment** you can sign in to. Note your tenant ID (the `abc12345` in `https://abc12345.apps.dynatrace.com`).
- [ ] **Permission to create an access token** with the `openTelemetryTrace.ingest` and `metrics.ingest` scopes.
- [ ] **Permission to create a platform token** with the `storage:metrics:read`, `storage:spans:read` and `storage:buckets:read` scopes.

## Container runtime

The lab runs in two containers started with Docker Compose, so you need a runtime that provides both `docker` and `docker compose`.

- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** is the simplest option, but it requires a paid licence for many organisations.
- **[Rancher Desktop](https://rancherdesktop.io/)** is a free alternative. In its settings, choose the **dockerd (moby)** container engine, not containerd. The dev container uses the `docker` and `docker compose` commands, which only the dockerd engine provides.
- Any other runtime works if it provides working `docker` and `docker compose` commands (for example Colima, or Docker Engine on Linux).

Whichever you choose, make sure it is running before you open the dev container.

## AWS credentials

The tutorial code calls AWS Bedrock, so you need AWS credentials with permission to invoke Bedrock models and guardrails. You don't need the AWS CLI on your machine, because the dev container installs it for you. You only need a `~/.aws/credentials` file, because the dev container mounts your `~/.aws` folder.

### Required IAM permissions

Whatever credentials you use, the IAM identity needs the following policy.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-mantle:CallWithBearerToken"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock-mantle:CreateInference"
      ],
      "Resource": "arn:aws:bedrock-mantle:us-east-2:*:project/default"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:us-east-2::foundation-model/openai.gpt-oss-120b-1:0"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:GetGuardrail",
        "bedrock:ApplyGuardrail"
      ],
      "Resource": "arn:aws:bedrock:us-east-2:*:guardrail/*"
    }
  ]
}
```

Most steps call the model through the `bedrock-mantle` endpoint — that is what the first two statements cover. **Step 3 (Guardrails) is the exception.** AWS Bedrock Guardrails do not work through `bedrock-mantle` — the OpenAI compatibility layer has no parameter for attaching a guardrail. Step 3 calls the native `bedrock-runtime` `converse` API instead, which needs `bedrock:InvokeModel` to run the model plus `bedrock:GetGuardrail` and `bedrock:ApplyGuardrail` to attach and evaluate the guardrail. The third and fourth statements grant that.

### Create `~/.aws/credentials`

Make sure `~/.aws/credentials` exists and looks like this. Replace the placeholders with your own values:

```ini
[default]
aws_access_key_id = REPLACE_WITH_YOUR_ACCESS_KEY_ID
aws_secret_access_key = REPLACE_WITH_YOUR_SECRET_ACCESS_KEY
aws_session_token = REPLACE_WITH_YOUR_SESSION_TOKEN
```

Temporary credentials (access key ID starting with `ASIA`) need all three lines. Long-term IAM user keys (starting with `AKIA`) don't have a session token, so omit the last line. The region (`us-east-2`) is set by the dev container.

!!! warning "Keep keys out of git"
    `~/.aws/credentials` lives outside the repository, so it can't be committed by accident. Never paste keys into files inside the repository.

### Don't have credentials yet?

Ask your AWS administrator for temporary credentials (access key, secret key and session token) for an identity with the policy above. If you have a personal AWS account, you can create an IAM user instead:

1. In the [IAM console](https://console.aws.amazon.com/iam/), go to **Policies → Create policy**
2. Switch to the **JSON** editor, paste the policy above, and save it with a name like `BedrockInvokePolicy`
3. Go to **Users → Create user**, give it a name (e.g. `ai-lab`), and attach the `BedrockInvokePolicy` you just created
4. Open the new user, go to **Security credentials → Create access key**, choose **Other**, and download the key
5. Put the access key ID and secret access key in `~/.aws/credentials`. Omit the `aws_session_token` line.

## Check your readiness

Before you start, confirm that you can answer "yes" to each of these:

| Question | If no |
|---|---|
| Do `docker run hello-world` and `docker compose version` both succeed? | Start your container runtime, or install one that provides `docker` and `docker compose`. |
| Can you open the AWS Console and find **Amazon Bedrock**? | Ask your AWS administrator for access. |
| Is `us-east-2` available to you for Bedrock? | Ask your AWS administrator to enable it. |
| Can you open **Access tokens** in Dynatrace (`Ctrl / Cmd + k`)? | Ask your Dynatrace administrator for token permissions. |
| Can you open [https://myaccount.dynatrace.com/platformTokens](https://myaccount.dynatrace.com/platformTokens)? | Ask your Dynatrace administrator for access to Account Management. |

## Security reminders

- Never commit credentials, tokens or `.devcontainer/.env` to git.
- IAM access keys don't expire. If you created an IAM user for this lab, delete the user and keys when the lab is over.

## Next step

Once everything above is ticked, continue to **[Setup](setup.md)**.
