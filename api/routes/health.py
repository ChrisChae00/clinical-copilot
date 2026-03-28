"""

This module defines the /health endpoint for the API, which checks if the Ollama LLM server is healthy and available.

"""

from fastapi import APIRouter, HTTPException
from llm.client import is_ollama_healthy

router = APIRouter()


@router.get("/health")
async def health():
    """
    Endpoint to check if the API and Ollama are healthy.

    Returns 200 OK if healthy

    503 if Ollama is unavailable

    Example curl command:
    curl http://localhost:8000/health

    """
    ok = await is_ollama_healthy()
    if not ok:
        raise HTTPException(status_code=503, detail="Ollama unavailable")
    return {"ok": True}
