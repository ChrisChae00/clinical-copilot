"""
This module defines the API routes for the autofill feature.
It accepts a payload with the following structure:
{
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
    API endpoint for autofill feature. It accepts a JSON body with "context" and "fields",
    builds a prompt for the LLM, and returns the LLM response as JSON.
    """

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Request body must be valid JSON",
        ) from e

    context, fields = _extract_autofill_body(body)
    prompt = _build_autofill_prompt(context=context, fields=fields)

    try:
        llm_response = await get_llm_response_json(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_AUTOFILL,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return llm_response


def _extract_autofill_body(body) -> tuple[object, list[object]]:
    """
    extract "context" and "fields" from the request body
    """
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Request body must be a JSON object"
        )

    context = body.get("context")
    fields = body.get("fields")

    if context is None:
        raise HTTPException(
            status_code=400, detail="context is required in the request body"
        )

    if not isinstance(fields, list):
        raise HTTPException(
            status_code=400, detail="fields is required and must be a list"
        )

    return context, fields


def _build_autofill_prompt(context: object, fields: list[object]) -> str:
    """
    builds the prompt to send to LLM
    """

    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    fields_json = json.dumps(fields, ensure_ascii=False, indent=2)

    return (
        "Resolve autofill values for the provided fields using the provided context.\n\n"
        "### CONTEXT ###\n"
        f"{context_json}\n\n"
        "### FIELDS ###\n"
        f"{fields_json}\n"
    )
