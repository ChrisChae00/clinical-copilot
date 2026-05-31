"""
This module defines the /generate-json endpoint for the API,

which takes a prompt and returns a json response from the LLM.
"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json

router = APIRouter()


@router.post("/generate-json", dependencies=[Depends(require_api_key)])
async def generate_json(request: Request):
    """
    /generate-json endpoint that takes a JSON body with a "prompt" field and returns the LLM response

    example payload:
    {
        "prompt": "Summarize patient history",
        "context": {
            "patient_name": "John Doe",
            "age": 45,
            "diagnosis": "Hypertension"
        },
        "additional_system_prompt": "You are a helpful assistant for summarizing patient information.",
        "images_b64": ["base64-encoded-image-string1", "base64-encoded-image-string2"]
    }

    """

    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    prompt = body.get("prompt")
    context = body.get("context")  # optional  dict extracted from EMR page DOM
    images_b64 = body.get("images_b64")  # optional list of base64-encoded images

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(
            status_code=400, detail="prompt is required and must be a non-empty string"
        )

    if context is not None and not isinstance(context, dict):
        raise HTTPException(
            status_code=400, detail="context must be a JSON object if provided"
        )

    try:
        return await get_llm_response_json(
            prompt=prompt, context=context, images_b64=images_b64
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
