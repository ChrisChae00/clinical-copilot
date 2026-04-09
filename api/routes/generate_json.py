"""
This module defines the /generate-json endpoint for the API,

which takes a prompt and optional context and returns a json response from the LLM.
"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json

router = APIRouter()


def _normalize_context(context: object) -> str:
    """
    Convert context into a string for prompt injection.

    Accepts:
    - None
    - string
    - any JSON-serializable object
    """
    if context is None:
        return ""

    if isinstance(context, str):
        return context.strip()

    try:
        return json.dumps(context, ensure_ascii=False, indent=2)
    except TypeError as e:
        raise HTTPException(
            status_code=400,
            detail="context must be a string, null, or a JSON-serializable value",
        ) from e


def _build_prompt(prompt: str, context: str) -> str:
    """
    Build the final prompt sent to the LLM.
    If context is empty, return the prompt unchanged.
    """
    prompt = prompt.strip()
    context = context.strip()

    if not context:
        return prompt

    return "### CONTEXT ###\n" f"{context}\n\n" "### USER PROMPT ###\n" f"{prompt}"


@router.post("/generate-json", dependencies=[Depends(require_api_key)])
async def generate_json(request: Request):
    """
    /generate-json endpoint that takes a JSON body with:
    - "prompt": required non-empty string
    - "context": optional string or JSON value

    Example request body:
    {
        "prompt": "Extract the active medication as JSON",
        "context": {
            "patient": {
                "name": "Ryan Tu"
            },
            "medications": []
        }
    }
    """

    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(
            status_code=400, detail="Request body must be valid JSON"
        ) from e

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Request body must be a JSON object"
        )

    prompt = body.get("prompt")
    raw_context = body.get("context", None)

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(
            status_code=400,
            detail="prompt is required and must be a non-empty string",
        )

    context = _normalize_context(raw_context)
    final_prompt = _build_prompt(prompt=prompt, context=context)

    try:
        return await get_llm_response_json(prompt=final_prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
