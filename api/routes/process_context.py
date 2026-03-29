"""
***WIP Currently not fully reliable.***

This module defines the API endpoint for processing the DOM into context that can be used by the LLM.

It accepts:
- "html": raw HTML of the current page
- "current-context": the current accumulated context (json)

example payload:
    {
        "html": "<html>...</html>",
        "current-context": { ...json... }
    }

example response:
    {
        "complete_context": { ...json... }
    }

"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json
from llm.prompts import SYSTEM_PROMPT_PROCESS_CONTEXT

router = APIRouter()


def extract_process_context_body(body) -> tuple[str, object]:
    """
    Helper function to validate and extract html and current_context from the request body.

    example payload:
    {
        "html": "<html>...</html>",
        "current-context": { ...json... }
    }

    example return:
    (
        "<html>...</html>",
        { ...json... }
    )
    """

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Request body must be a JSON object"
        )

    html = body.get("html")
    current_context = body.get("current-context", None)

    if not isinstance(html, str) or not html.strip():
        raise HTTPException(
            status_code=400,
            detail="html is required and must be a non-empty string",
        )

    return html, current_context


def build_process_context_prompt(html: str, current_context: object | None) -> str:
    """
    Helper function that builds the main prompt for the context-processing LLM call.

    Note: The system prompt contains the instructions (SYSTEM_PROMPT_PROCESS_CONTEXT). This prompt contains only the inputs.
    """
    current_context_json = (
        json.dumps(current_context, ensure_ascii=False, indent=2)
        if current_context is not None
        else "null"
    )

    return (
        "### INPUT ###\n"
        "HTML:\n"
        f"{html}\n\n"
        "CURRENT_CONTEXT:\n"
        f"{current_context_json}"
    )


@router.post("/process-context", dependencies=[Depends(require_api_key)])
async def process_context(request: Request):
    """
    /process-context endpoint that takes a JSON body with:
    - "html": raw HTML of the current page
    - "current-context": the current accumulated context (any JSON value)

    It sends both to the LLM, which returns a complete updated context object.

    example request body:
    {
        "html": "<html>...</html>",
        "current-context": { ...json... }
    }

    example response body:
    {
        "complete_context": { ...json... }
    }

    """
    # receive html and current context
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Request body must be valid JSON",
        ) from e

    html, current_context = extract_process_context_body(body)
    prompt = build_process_context_prompt(html=html, current_context=current_context)

    # call llm
    try:
        complete_context = await get_llm_response_json(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_PROCESS_CONTEXT,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    if not isinstance(complete_context, dict):
        raise HTTPException(
            status_code=502,
            detail="LLM response must be a JSON object",
        )

    return complete_context
