"""
This module defines the API routes for the autofill feature.

NOTE: edit SYSTEM_PROMPT_AUTOFILL in api\llm\prompts.py to change supprted field types, response format, etc.

"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json
from llm.prompts import SYSTEM_PROMPT_AUTOFILL
from pydantic import BaseModel

router = APIRouter()


class AutofillRequest(BaseModel):
    prompt: str | None = None
    context: str
    images_b64: list[str] | None = None
    fields: list[dict]


@router.post("/autofill", dependencies=[Depends(require_api_key)])
async def autofill(request: AutofillRequest):
    """
    API endpoint for autofill feature.
    It accepts a JSON body with "prompt", "context" and "fields" and return a JSON response with the fields that needs to be filled and their corresponding values.

    REQUEST:
    {
        "prompt": "Fill in reason for visit as: severe headache",

        "context": "

            ##patient info##
            patient_name: joe mama
            age: 45
            diagnosis: Hypertension

            ##chat history##
            user: sdfsdafdsada
            assistant: sdfdsafdsad",

        "images_b64": ["base64-encoded-image-string1", "base64-encoded-image-string2"],

        "fields": [
            {
            "id": "alliergies",
            "label": "allergies",
            "type": "text box",
            },
            {
            "id": "some_drop_down",
            "label": "idk_some_drop_down",
            "type": "select",
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

    - prompt (str optional): an optional prompt to guide the LLM's response.
    - context (str required): context that has been accumulated from all previous interactions to include in the prompt.
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.
    - fields (list[dict] required): a list of fields to fill indicating their type (text, radio button, select, dropdown, etc)

    NOTE: the structure of the json keys itself are not rigid, BUT there MUST be "context", "fields", "prompt" keys in the payload

    RESPONSE:
    {
      "fills": [
        {
          "field_id": "patient_name",
          "type": "text box",
          "value": "John Smith",
          "confidence": 0.99
        },
        {
          "field_id": "some_drop_down",
          "type": "select",
          "value": "option_1",
          "confidence": 0.85
        }
      ],
    }

    - fills (list): a list of fields to be filled with the following keys:
        - field_id (str): the id of the field
        - type (str): the type of the field "text box", "select", "radio button", "check box", etc so that the corresponding action can be performed on extension side.
        - value (str):
        - confidence (float): 0.0 to 1.0

    Field types and value formats (NOTE: SEE/EDIT SYSTEM_PROMPT_AUTOFILL in api/llm/prompts.py to change):
    - text: string
    - textarea: string
    - number: number or numeric string
    - date: string in YYYY-MM-DD format when possible
    - time: string in HH:MM format when possible
    - datetime: string in YYYY-MM-DDTHH:MM format when possible
    - select: exact option value from the provided options
    - multiselect: list of exact option values from the provided options
    - checkbox: true or false
    - checkbox_group: list of exact option values to check
    - radio: exact option value from the provided options
    - contenteditable: string
    - combobox: exact option value if available, otherwise exact visible label

    """

    if not request.prompt and not request.context:
        raise HTTPException(
            status_code=400,
            detail="At least one of prompt or context must be provided",
        )

    if not request.fields or len(request.fields) == 0:
        raise HTTPException(status_code=400, detail="fields must be a non-empty list")

    input = {
        "prompt": request.prompt or "",
        "context": request.context or "",
        "fields": request.fields,
    }

    prompt = f"""
    You are given the following autofill request as JSON.

    Autofill request:
    {json.dumps(input, ensure_ascii=False, indent=2)}

    """

    response = await get_llm_response_json(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_AUTOFILL,
        images_b64=request.images_b64 or [],
    )

    # print("DEBUG: LLM response for autofill:", response)
    return response
