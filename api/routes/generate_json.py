"""
This module defines the /generate-json endpoint for the API,

which takes a prompt and returns a json response from the LLM.
"""

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json

router = APIRouter()


@router.post("/generate-json", dependencies=[Depends(require_api_key)])
async def generate_json(request: Request):
    """
    /generate-json endpoint that takes a JSON body with a "prompt" field and returns the LLM response

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
        return await get_llm_response_json(prompt=prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
