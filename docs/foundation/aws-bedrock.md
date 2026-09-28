# AWS Bedrock

## What is AWS Bedrock?

AWS Bedrock is Amazon's managed AI service. It lets you call AI models from multiple providers (Anthropic, Meta, Mistral, and others) through a single AWS API, without managing any infrastructure yourself.

Think of it as a marketplace for AI models, where AWS handles authentication, scaling, and availability.

## What is AWS Bedrock Mantle?

The tutorials use a specific endpoint: `https://bedrock-mantle.us-east-2.api.aws/v1`

**Mantle** is an AWS Bedrock compatibility layer that exposes an **OpenAI-compatible API**. This is significant because:

- You can use the standard `openai` Python library (not a custom AWS SDK)
- Any code written for OpenAI works with minimal changes
- Authentication uses AWS credentials (via a token generator), not an OpenAI API key

This is why you'll see:

```python
from openai import OpenAI
from aws_bedrock_token_generator import provide_token

client = OpenAI(
    api_key=provide_token(),   # AWS credentials wrapped as a token
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)
```

The `provide_token()` function handles AWS authentication (SigV4 signing) behind the scenes and returns a short-lived token that the OpenAI client uses as its API key.

## The model we use

Our tutorials use `openai.gpt-oss-120b`, a large language model available via Bedrock Mantle. The `openai.` prefix is part of the model identifier in the Mantle namespace.

## Why Bedrock?

We use Bedrock for a few reasons:

- It's enterprise-grade and production-ready
- AWS handles model updates and availability
- It supports the OpenAI-compatible API, which keeps our code portable
- Many organisations already have AWS infrastructure in place

The observability patterns in these tutorials work equally well with other providers (Anthropic's API directly, Azure OpenAI, etc.). Only the client setup differs.

## Ready to run the code?

See [Setup](setup.md) for how to configure your AWS credentials, Dynatrace tokens, and Python environment.
