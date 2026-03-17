import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="Clinical Ally LLM Proxy")

# TODO Sprint 2: restrict origins — moz-extension:// UUIDs are unpredictable in Sprint 1
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

OLLAMA_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434/api/generate",
)
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

# Cloudflare Access headers (required when OLLAMA_URL points to a CF-protected host)
CF_CLIENT_ID = os.environ.get("CF_ACCESS_CLIENT_ID", "")
CF_CLIENT_SECRET = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")


class AskRequest(BaseModel):
    prompt: str
    patient_context: str = ""


class AskResponse(BaseModel):
    response: str


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    # TODO: incorporate patient_context into system prompt once extraction is implemented
    # TODO: add prompt guardrails (refuse requests for PII, unsafe medical advice, etc.)
    system_prompt = (
        "You are Clinical Ally, an AI assistant for healthcare professionals using OpenEMR. "
        "Provide concise, evidence-based clinical information. "
        "Always remind users to apply clinical judgment. "
        "Do not store or repeat any patient identifiers."
    )

    ollama_payload = {
        "model": MODEL,
        "prompt": request.prompt,
        "system": system_prompt,
        "stream": False,  # TODO Sprint 2: enable streaming for faster perceived response
    }

    headers = {"Content-Type": "application/json"}
    if CF_CLIENT_ID and CF_CLIENT_SECRET:
        headers["CF-Access-Client-Id"] = CF_CLIENT_ID
        headers["CF-Access-Client-Secret"] = CF_CLIENT_SECRET

    # 60s timeout — LLM generation can be slow on CPU
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(OLLAMA_URL, json=ollama_payload, headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot reach Ollama at {OLLAMA_URL}. Is it running?",
            )
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama returned error: {e.response.status_code}",
            )

    data = resp.json()
    return AskResponse(response=data.get("response", ""))
