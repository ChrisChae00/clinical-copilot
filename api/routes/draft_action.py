"""
POST /draft-action

Generates a draft document for a clinical action (referral letter,
lab requisition, prescription note, etc.) using patient context.

Request body:
{
  "action": {
    "type": "referral|lab_order|prescription|follow_up|imaging|note|alert",
    "title": "...",
    "description": "...",
    "details": {}
  },
  "context": {}  // optional patient EMR context
}

Response:
{
  "draft": "Full draft text ready to copy/paste"
}
"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_str
from llm.prompts import SYSTEM_PROMPT_DRAFT_ACTION

router = APIRouter()

VALID_TYPES = {"referral", "lab_order", "prescription", "follow_up", "imaging", "note", "alert"}


@router.post("/draft-action", dependencies=[Depends(require_api_key)])
async def draft_action(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from e

    action = body.get("action")
    context = body.get("context")

    if not isinstance(action, dict):
        raise HTTPException(status_code=400, detail="action must be a JSON object")

    action_type = action.get("type")
    if action_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"action.type must be one of: {', '.join(VALID_TYPES)}")

    if context is not None and not isinstance(context, dict):
        raise HTTPException(status_code=400, detail="context must be a JSON object if provided")

    prompt = _build_prompt(action, context)

    try:
        draft = await get_llm_response_str(prompt=prompt, system_prompt=SYSTEM_PROMPT_DRAFT_ACTION)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {"draft": draft.strip()}


def _build_prompt(action: dict, context: object) -> str:
    parts = [
        f"Generate a draft for the following clinical action:\n\n",
        f"Type: {action.get('type')}\n",
        f"Title: {action.get('title', '')}\n",
        f"Description: {action.get('description', '')}\n",
    ]

    details = action.get("details")
    if details:
        parts.append(f"Details: {json.dumps(details, ensure_ascii=False)}\n")

    if context:
        parts.append("\n### PATIENT CONTEXT ###\n")
        parts.append(json.dumps(context, ensure_ascii=False, indent=2))

    return "".join(parts)
