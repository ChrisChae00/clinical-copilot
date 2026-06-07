"""
This module defines the /chat endpoint for the API,

which takes a prompt and returns a json response from the LLM.
"""

import json

from auth import require_api_key
from dom.dom_processor import clean_dom
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_json, get_llm_response_str
from llm.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT_PROCESS_CLEANED_DOM
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    context: str | None = None
    raw_html: str | None = None
    system_prompt: str | None = None
    images_b64: list[str] | None = None


@router.post("/chat", dependencies=[Depends(require_api_key)])
async def chat(request: ChatRequest):
    """
    /chat endpoint that returns a LLM response (in JSON format)

    REQUEST:
    fields:
    - prompt (str)
    - system_prompt (str, optional): REPLACE the default system prompt. If not provided, just the BASE_SYSTEM_PROMPT will be used.
    - context (str, optional): context that has been accumulated from all previous interactions to include in the prompt. Defaults to None.
    - raw_html (str, optional): Raw HTML of the current page to include in the prompt. Defaults to None.
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.

    example request payload:
    {
        "prompt": "perform some task",

        "context": "
        ##patient info##
        patient_name: John Doe
        age: 45
        diagnosis: Hypertension

        ##chat history##
        user: sdfsdafdsada
        assistant: sdfdsafdsad
        ",

        "raw_html": "<html>...</html>",  # optional raw HTML str to provide more/new context

        "system_prompt": "instructions for llm to be used instead of the default",

        "images_b64": ["base64-encoded-image-string1", "base64-encoded-image-string2"]
    }

    RESPONSE:
    response payload format:
    - response (str): the LLM's text response to the prompt
    - updated_context (str): an updated version of the accumulated context based on the new input, if applicable. if nothing new is found, it returns the original context.
    - actions (list): a list of action/tool names to be executed (in sequence order) based on the input, which may be empty if no specific actions are suggested
    list of tools are defined in the default system prompt

    example response payload:
    {
        "response": "John Doe is a 45-year-old patient diagnosed with...",
        "updated_context": "##patient info##\npatient_name: John Doe\nage: 45\ndiagnosis: Hypertension\n\n##chat history##\nuser: sdfsdafdsada\nassistant: sdfdsafdsad\n\n##new info from latest prompt##\n... any new info extracted from the latest prompt or raw_html that can be added to the context ...",
        "actions": ["action_name_1", "action_name_2", ...]
    }
    """

    try:
        response = await _get_chat_response(
            prompt=request.prompt,
            context=request.context,
            raw_html=request.raw_html,
            images_b64=request.images_b64,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return response


async def _get_chat_response(
    prompt: str,
    context: str | None = None,
    raw_html: str | None = None,
    images_b64: list[str] | None = None,
) -> dict:
    """
    helper function to get LLM response for the /chat endpoint.
    main logic for constructing the prompt and calling the LLM client

    args:
    - prompt (str): MANDATORY
    - context (str, optional): context that has been accumulated from all previous interactions to include in the prompt. Defaults to None.
    - raw_html (str, optional): Raw HTML of the current page to include in the prompt. Defaults to None.
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.

    returns:
    - response (dict): the LLM response in dict/json format
    """

    if not prompt or not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must be a non-empty string")

    # build prompt
    prompt = "### USER PROMPT ###\n" + prompt

    # add context to prompt
    if context and context.strip():
        prompt = prompt + "\n\n" "### CURRENT ACCUMULATED CONTEXT ###\n" + context

    # if raw_html is provided, process it and add to the prompt
    if raw_html and raw_html.strip():
        # cleaned page
        cleaned_page = await clean_dom(raw_html)

        # NOTE: can use the llm furthur to extract info if needed. commented out for now.
        # cleaned_page = await get_llm_response_str(
        #     system_prompt=SYSTEM_PROMPT_PROCESS_CLEANED_DOM, prompt=cleaned_page
        # )
        prompt = (
            prompt + "\n\n" "### CURRENT USER WEBPAGE INFORMATION ###\n" + cleaned_page
        )

    # call llm client to get response
    response = await get_llm_response_json(
        system_prompt=CHAT_SYSTEM_PROMPT, prompt=prompt, images_b64=images_b64
    )

    return response
