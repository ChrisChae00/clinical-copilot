"""
This module defines the API routes for the autofill feature.
It accepts a payload with the following structure:
{
    "prompt": "optional prompt to guide the LLM's response, e.g. 'Fill in the following fields based on the context'",
    "context": { ...json... } // context about the user and the page
    "fields": [
        {
        "id": "patient_xxx",
        "label": "patient xxx",
        "type": "text",
        "required": true
        },
        {
        "id": "some_drop_down",
        "label": "idk_some_drop_down",
        "type": "select",
        "required": false,
        "options": [
            {
                "value": "option_1",
                "label": "Option 1"
            },
            {
                "value": "option_2",
                "label": "Option 2"
            }
            ]
        },
    ]
}
NOTE: the structure is not rigid, and can be anything since the LLM will be parsing it BUT there MUST be "context" and "fields" in the payload

The response will be a JSON object with the following structure:
{
  "fills": [
    {
      "field_id": "patient_name",
      "action": "fill",
      "value": "John Smith",
      "confidence": 0.99
    },
    {
      "field_id": "some_drop_down",
      "action": "select",
      "value": "option_1",
      "confidence": 0.85
    }
  ],
}

"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json
from llm.prompts import SYSTEM_PROMPT_AUTOFILL

router = APIRouter()


@router.post("/autofill", dependencies=[Depends(require_api_key)])
async def autofill(request: Request):
    """
    API endpoint for autofill feature. It accepts a JSON body with "prompt" (optional), "context" and "fields",
    builds a prompt for the LLM, and returns the LLM response as JSON.
    """

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Request body must be valid JSON",
        ) from e

    prompt, context, fields = _extract_autofill_body(body)
    llm_prompt = _build_autofill_prompt(prompt, context, fields)
    try:
        llm_response = await get_llm_response_json(
            prompt=llm_prompt, system_prompt=SYSTEM_PROMPT_AUTOFILL
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return llm_response


def _extract_autofill_body(body) -> tuple[str, dict, list[dict]]:
    """
    extract "prompt", "context" and "fields" from the request body
    """
    prompt = body.get("prompt", "")
    context = body.get("context")
    fields = body.get("fields")
    if not isinstance(context, dict):
        raise HTTPException(
            status_code=400, detail="context is required and must be a JSON object"
        )
    if not isinstance(fields, list) or not all(
        isinstance(field, dict) for field in fields
    ):
        raise HTTPException(
            status_code=400,
            detail="fields is required and must be a list of JSON objects",
        )
    return prompt, context, fields


def _build_autofill_prompt(prompt: str, context: dict, fields: list[dict]) -> str:
    """
    build a prompt for the LLM based on the input prompt, context and fields
    """
    fields_str = json.dumps(fields, ensure_ascii=False, indent=2)
    contextual_prompt = (
        f"{prompt}\n\n"
        "### CONTEXT ###\n"
        "The following information about the user and the page may be helpful for filling in the fields. "
        "Use it to give relevant responses.\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        "### FIELDS TO FILL ###\n"
        "The following is a list of fields to fill. Each field has an id, label, type, and required boolean. "
        "Use this information to understand what each field is asking for.\n"
        f"{fields_str}\n\n"
    )
    return contextual_prompt
