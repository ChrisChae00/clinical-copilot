"""
This module defines the /generate endpoint for the API, which takes a prompt and returns a response from the LLM.
"""

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response

router = APIRouter()


@router.post("/generate", dependencies=[Depends(require_api_key)])
async def generate(request: Request):
    """
    /generate endpoint that takes a JSON body with a "prompt" field and returns the LLM response

    Example request body:

    {
    "prompt": "What da dawg doing?"
    }

    Example curl command:
    curl -X POST http://localhost:8000/generate -H "Content-Type: application/json" -H "X-API-Key: api-key-placeholder" -d "{\"prompt\":\"New fone, who dis?\"}"

    """

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    prompt = body.get("prompt")

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(
            status_code=400, detail="prompt is required and must be a non-empty string"
        )

    try:
        return await get_llm_response(prompt=prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
