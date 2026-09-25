# Team AI proxy — forwards OpenAI-compatible requests to Bedrock Mantle.
# Point your tools at http://localhost:8000 instead of Bedrock Mantle directly.
#
# Run with: uvicorn app:app --port 8000

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aws_bedrock_token_generator import provide_token

BEDROCK_MANTLE_URL = "https://bedrock-mantle.us-east-2.api.aws/v1/chat/completions"

app = FastAPI()


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model_name = body.get("model", "unknown")
    print(f"Request received — model: {model_name}")

    async with httpx.AsyncClient() as http:
        upstream = await http.post(
            BEDROCK_MANTLE_URL,
            json=body,
            headers={
                "Authorization": f"Bearer {provide_token()}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )

    return JSONResponse(content=upstream.json(), status_code=upstream.status_code)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
