"""
Client that interfaces with the LLM (Ollama)

functions:

get_llm_response_str() - get string response from LLM
- prompt
- system_prompt
- images_b64 (optional): list of base64-encoded images to include in the prompt

get_llm_response_json() - get json reponse from LLM
- prompt
- system_prompt
- images_b64 (optional): list of base64-encoded images to include in the prompt

is_ollama_healthy() - check if ollama is reachable


for reference, example ollama response structure:
    {
    "model": "llama3.2:1b",
    "created_at": "2026-03-26T19:13:47.016445677Z",
    "response": "hihi",
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

    DO NOT USE THE OLLAMA RESPONSE FOR CONTEXT KEEPING

"""

import json

import httpx

# import values for prod
from config import (
    LLM_TIMEOUT,
    MAX_CONTEXT_LEN,
    MODEL_NAME,
    OLLAMA_CF_ACCESS_CLIENT_ID,
    OLLAMA_CF_ACCESS_CLIENT_SECRET,
    OLLAMA_URL,
)

# FOR TESTING PURPOSES
# test values for running this file by itself (w.o docker)
# will be overridden in prod by values from config.py
# MAX_CONTEXT_LEN = 8192
# MODEL_NAME = "qwen2.5vl:7b"
# OLLAMA_URL = "http://localhost:11434"
# OLLAMA_CF_ACCESS_CLIENT_ID = insert
# OLLAMA_CF_ACCESS_CLIENT_SECRET = insert


async def get_llm_response_str(
    prompt: str, system_prompt: str, images_b64: list[str] | None = None
) -> str:
    """
    simply gets a text response from LLM

    used for summarization or other tasks internally. should not be exposed as an endpoint.
    use the json version get_llm_response_json() for structured json response.
    For internal use, not to be exposed as an endpoint.

    args:
    - prompt (str): MANDATORY
    - system_prompt (str): MANDATORY
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.

        returns:
    - response (str)
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be a non-empty string")

    payload = {
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": prompt,
        "images": images_b64 or [],
        "stream": False,
        "options": {"num_ctx": MAX_CONTEXT_LEN},
    }

    try:
        async with httpx.AsyncClient(timeout=_llm_timeout()) as client:
            # response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload) -> this is for when we host local ollama (no cloudflare)
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
                headers=_ollama_headers(),
            )
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Ollama: {e}") from e

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama returned status code {response.status_code}: {response.text}"
        )

    data = response.json()
    return data["response"]


async def get_llm_response_json(
    prompt: str, system_prompt: str, images_b64: list[str] | None = None
) -> dict:
    """
    like the get_llm_response_str() but returns a json/dict response.

    for internal use, not to be exposed as an endpoint.

    args:
    - prompt (str): MANDATORY
    - system_prompt (str): MANDATORY
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.

    returns:
    - response (dict/json)
    """

    if not prompt or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be a non-empty string")

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
        async with httpx.AsyncClient(timeout=_llm_timeout()) as client:
            # response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload) -> this is for when we host local ollama (no cloudflare)
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
                headers=_ollama_headers(),
            )
    except httpx.RequestError as e:
        raise RuntimeError(f"Could not reach Ollama: {e}") from e

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama returned status code {response.status_code}: {response.text}"
        )

    # extract response and return as json/dict
    try:
        data = response.json()
    except ValueError as e:
        raise RuntimeError(f"Ollama returned invalid JSON: {response.text}") from e

    try:
        return json.loads(data["response"])
    except (KeyError, ValueError) as e:
        raise RuntimeError(
            f"Ollama response does not contain valid 'response' field: {data}"
        ) from e


async def is_ollama_healthy() -> bool:
    """
    Check if Ollama is reachable and responding to requests
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            # response = await client.get(f"{OLLAMA_URL}/api/tags") -> this is for when we host local ollama (no cloudflare)
            response = await client.get(
                f"{OLLAMA_URL}/api/tags",
                headers=_ollama_headers(),
            )
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


def _llm_timeout() -> httpx.Timeout:
    """
    Helper func to build the httpx timeout for Ollama calls.

    Connect/write/pool stay tight since those failures should surface fast;
    read is generous (LLM_TIMEOUT, default 300s) since generation for
    heavy payloads (e.g. autofill scanning a full form) can legitimately
    take a couple of minutes, especially without GPU acceleration.
    """
    return httpx.Timeout(connect=10.0, read=LLM_TIMEOUT, write=30.0, pool=LLM_TIMEOUT)


def _ollama_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    """
    Helper func to get header for ollama request for clouflare access.
    """

    if OLLAMA_CF_ACCESS_CLIENT_ID and OLLAMA_CF_ACCESS_CLIENT_SECRET:
        headers["CF-Access-Client-Id"] = OLLAMA_CF_ACCESS_CLIENT_ID
        headers["CF-Access-Client-Secret"] = OLLAMA_CF_ACCESS_CLIENT_SECRET

    return headers


# FOR TESTING PURPOSES
# if __name__ == "__main__":

#     import asyncio

#     prompt = "who is my patient? give me all the info"

#     context = """
#         current_medications: Lisinopril,Metformin
#     """
#     image_path = "tests/test_report.png"

#     with open("tests/testpage1.html", "r", encoding="utf-8") as f:
#         raw_html = f.read()

#     with open(image_path, "rb") as f:
#         image_bytes = f.read()
#     import base64

#     image_b64 = base64.b64encode(image_bytes).decode("utf-8")

#     response = asyncio.run(
#         get_llm_response_json(
#             prompt=prompt,
#             system_prompt="help me extract useful information from this webpage and image",
#             images_b64=[image_b64],
#         )
#     )

#     print(response)
