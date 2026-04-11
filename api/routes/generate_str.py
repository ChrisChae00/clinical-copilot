"""
This module defines the /generate endpoint for the API, which takes a prompt and returns a response from the LLM.
"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_str

router = APIRouter()


@router.post("/generate-str", dependencies=[Depends(require_api_key)])
async def generate_str(request: Request):
    """
    /generate-str endpoint that takes a JSON body with a "prompt" field and returns the LLM response

    Example request body:

    {
    "prompt": "What da dawg doing?"
    }

    Example curl command:
    curl -X POST http://localhost:8000/generate-str -H "Content-Type: application/json" -H "X-API-Key: api-key-placeholder" -d "{\"prompt\":\"New fone, who dis?\"}"

    """

    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    prompt = body.get("prompt")
    context = body.get("context")  # optional dict extracted from EMR page DOM

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(
            status_code=400, detail="prompt is required and must be a non-empty string"
        )

    if context is not None and not isinstance(context, dict):
        raise HTTPException(
            status_code=400, detail="context must be a JSON object if provided"
        )

    try:
        return await get_llm_response_str(prompt=prompt, context=context)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
