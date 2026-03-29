"""
Client that interfaces with the LLM (Ollama)
"""

import json

import httpx
from config import MODEL_NAME, OLLAMA_URL
from llm.prompts import SYSTEM_PROMPT


# str version
async def get_llm_response_str(prompt: str) -> str:
    """

    Send a prompt to the Ollama LLM server and return the response.
    calls the /api/generate endpoint of in Ollama
    args:
        prompt (str): The prompt to send to the LLM
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

    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
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
    prompt: str, system_prompt: str = SYSTEM_PROMPT
) -> dict:
    """
    Calls the /api/generate endpoint of in Ollama in json mode so it always return a json

    args:
    - prompt (str)
    - system_prompt (str)
    returns:
    - response (dict/json)
    raises:
        ValueError: If the prompt is invalid
        RuntimeError: If there is an issue communicating with Ollama or if the LLM returns invalid JSON

    note: system_prompt is optional. It default to SYSTEM_PROMPT.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    payload = {
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
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
        print(f"WARNING: Ollama health check failed (status {e.response.status_code}): {e}")
        return False
