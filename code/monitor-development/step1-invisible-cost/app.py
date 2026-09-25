"""Developer AI assistant — code explanation, test generation, security review. No observability."""

from openai import OpenAI
from aws_bedrock_token_generator import provide_token

client = OpenAI(
    api_key=provide_token(),
    base_url="https://bedrock-mantle.us-east-2.api.aws/v1",
    project="default",
)

MODEL = "anthropic.claude-3-5-haiku-20241022"

FUNCTION_UNDER_REVIEW = """
def process_batch(records, transform_fn, batch_size=100):
    results = []
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        transformed = [transform_fn(r) for r in batch]
        results.extend(transformed)
    return results
"""

# Task 1: explain the function
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": f"Explain what this Python function does:\n\n{FUNCTION_UNDER_REVIEW}",
        }
    ],
)
print("=== Explanation ===")
print(response.choices[0].message.content)

# Task 2: generate unit tests
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": f"Write pytest unit tests for this function:\n\n{FUNCTION_UNDER_REVIEW}",
        }
    ],
)
print("\n=== Unit Tests ===")
print(response.choices[0].message.content)

# Task 3: security review
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "user",
            "content": f"Review this function for security issues:\n\n{FUNCTION_UNDER_REVIEW}",
        }
    ],
)
print("\n=== Security Review ===")
print(response.choices[0].message.content)
