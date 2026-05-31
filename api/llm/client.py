"""
Client that interfaces with the LLM (Ollama)
"""

import json
from typing import AsyncGenerator

import httpx

if __name__ == "__main__":
    # test values for running this file by itself (w.o docker)
    MAX_CONTEXT_LEN = 8192
    MODEL_NAME = "qwen2.5vl:7b"
    OLLAMA_URL = "http://localhost:11434"
    from .prompts import BASE_SYSTEM_PROMPT
else:
    # import values for prod
    from config import MAX_CONTEXT_LEN, MODEL_NAME, OLLAMA_URL
    from llm.prompts import BASE_SYSTEM_PROMPT


def _build_contextual_prompt(prompt: str, context: dict | None = None) -> str:
    """
    Append structured context directly to the user message so the model can
    consider it alongside the original prompt.
    """

    if context is None:
        return prompt

    context_str = json.dumps(context, ensure_ascii=False, indent=2)
    return (
        f"{prompt}\n\n"
        "### CURRENT PATIENT CONTEXT ###\n"
        "The following information was extracted from the current EMR page"
        "Use it to give context-aware, relevant responses.\n"
        f"{context_str}"
    )


async def stream_llm_response(
    prompt: str,
    context: dict | None = None,
    additional_system_prompt: str | None = None,
    images_b64: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream tokens from Ollama as server-sent events.
    Yields SSE-formatted strings: `data: <token>\n\n`
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    if additional_system_prompt:
        system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + additional_system_prompt
    else:
        system_prompt = BASE_SYSTEM_PROMPT

    prompt = _build_contextual_prompt(prompt, context)

    payload = {
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": prompt,
        "stream": True,
        "options": {"num_ctx": MAX_CONTEXT_LEN},
    }

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST", f"{OLLAMA_URL}/api/generate", json=payload
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama returned status code {response.status_code}"
                )
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    yield f"data: {json.dumps(token)}\n\n"
                if chunk.get("done"):
                    yield "data: [DONE]\n\n"
                    return


# str version
async def get_llm_response_str(
    prompt: str,
    context: dict | None = None,
    additional_system_prompt: str | None = None,
    images_b64: list[str] | None = None,
) -> str:
    """

    Send a prompt to the Ollama LLM server and return the response.
    calls the /api/generate endpoint of in Ollama
    args:
        prompt (str): The prompt to send to the LLM
        system_prompt (str, optional): Custom system prompt to be appended to the default prompt. If not provided, just the BASE_SYSTEM_PROMPT will be used.
        context (dict, optional): context in JSON format to include in the prompt. Defaults to None.
        images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.
    returns:
        response (str): The text response from the LLM
    raises:
        ValueError: If the prompt is invalid
        RuntimeError: If there is an issue communicating with Ollama or if Ollama returns an error


    raw response example:
    {
    "model": "llama3.2:1b",
    "created_at": "2026-03-26T19:13:47.016445677Z",
    "response": "Yo",
    "done": true,
    "done_reason": "stop",
    "context": [...],
    "total_duration": 21402465413,
    "load_duration": 20995589077,
    "prompt_eval_count": 30,
    "prompt_eval_duration": 2134529,
    "eval_count": 23,
    "eval_duration": 50131658
    }

    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    if additional_system_prompt:
        system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + additional_system_prompt
    else:
        system_prompt = BASE_SYSTEM_PROMPT

    # print(f"DEBUG: system prompt:\n{system_prompt}\n")

    prompt = _build_contextual_prompt(prompt, context)

    # print(f"DEBUG: prompt sent to LLM:\n{prompt}\n")

    payload = {
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": prompt,
        "images": images_b64 or [],
        "stream": False,
        "options": {"num_ctx": MAX_CONTEXT_LEN},
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Ollama: {e}") from e

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama returned status code {response.status_code}: {response.text}"
        )

    response_text = response.json().get("response", "")
    if not isinstance(response_text, str):
        raise RuntimeError("Ollama response is not a string")

    return response_text


# json version
async def get_llm_response_json(
    prompt: str,
    context: dict | None = None,
    additional_system_prompt: str | None = None,
    images_b64: list[str] | None = None,
) -> dict:
    """
    Calls the /api/generate endpoint of in Ollama in json mode so it always return a json

    args:
    - prompt (str)
    - system_prompt (str, optional): Custom system prompt to be appended to the default prompt. If not provided, just the BASE_SYSTEM_PROMPT will be used.
    - context (dict, optional): context in JSON format to include in the prompt. Defaults to None.
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.
    returns:
    - response (dict/json)
    raises:
        ValueError: If the prompt is invalid
        RuntimeError: If there is an issue communicating with Ollama or if the LLM returns invalid JSON
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    prompt = _build_contextual_prompt(prompt, context)

    if additional_system_prompt:
        system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + additional_system_prompt
    else:
        system_prompt = BASE_SYSTEM_PROMPT

    payload = {
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": prompt,
        "images": images_b64 or [],
        "stream": False,
        "format": "json",
        "options": {"num_ctx": MAX_CONTEXT_LEN},
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Ollama: {e}") from e

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama returned status code {response.status_code}: {response.text}"
        )

    # get response field (still str)
    try:
        response_json_str = response.json().get("response", "")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ollama returned a non-JSON HTTP response body: {e}") from e

    # parse the response string as json
    try:
        response_json = json.loads(response_json_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM response could not be parsed as JSON. Raw: {response_json_str!r}. Error: {e}"
        ) from e

    return response_json


async def is_ollama_healthy() -> bool:
    """
    Check if Ollama is reachable and responding to requests
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
        return True
    except httpx.RequestError as e:
        print(f"WARNING: Ollama health check failed (network): {e}")
        return False
    except httpx.HTTPStatusError as e:
        print(
            f"WARNING: Ollama health check failed (status {e.response.status_code}): {e}"
        )
        return False


if __name__ == "__main__":

    import asyncio

    prompt = "who is my patient? give me all the info"

    context = {
        "patient_name": "John Doe",
        "patient_age": 45,
        "current_medications": ["Lisinopril", "Metformin"],
    }
    image_path = "tests/test_report.png"

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    import base64

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = asyncio.run(
        get_llm_response_json(prompt=prompt, context=context, images_b64=[image_b64])
    )
    print("LLM response:", response)
