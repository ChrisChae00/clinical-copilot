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
        JSON
    }

"""

import json

from auth import require_api_key
from dom.dom_processor import process_dom
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json
from llm.prompts import SYSTEM_PROMPT_PROCESS_CONTEXT

router = APIRouter()


def _extract_process_context_body(body) -> tuple[str, object]:
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


def _build_process_context_prompt(
    processed_html: str, current_context: object | None
) -> str:
    current_context_json = (
        json.dumps(current_context, ensure_ascii=False, indent=2)
        if current_context is not None
        else "null"
    )

    return (
        "### INPUT ###\n"
        "EXTRACTED_PAGE:\n"
        f"{processed_html}\n\n"
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

    """
    # receive html and current context
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Request body must be valid JSON",
        ) from e

    html, current_context = _extract_process_context_body(body)
    processed_html = process_dom(html)
    prompt = _build_process_context_prompt(
        processed_html=processed_html,
        current_context=current_context,
    )

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
