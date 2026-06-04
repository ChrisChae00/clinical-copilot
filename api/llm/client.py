"""
Client that interfaces with the LLM (Ollama)
"""

import json

import httpx

if __name__ == "__main__":
    # test values for running this file by itself (w.o docker)
    MAX_CONTEXT_LEN = 8192
    MODEL_NAME = "qwen2.5vl:7b"
    OLLAMA_URL = "http://localhost:11434"
    from ..dom.dom_processor import clean_dom
    from .prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT_PROCESS_CLEANED_DOM
else:
    # import values for prod
    from config import MAX_CONTEXT_LEN, MODEL_NAME, OLLAMA_URL
    from dom.dom_processor import clean_dom
    from llm.prompts import CHAT_SYSTEM_PROMPT, SYSTEM_PROMPT_PROCESS_CLEANED_DOM


async def get_llm_response_json(
    prompt: str,
    context: str | None = None,
    raw_html: str | None = None,
    system_prompt: str = CHAT_SYSTEM_PROMPT,
    images_b64: list[str] | None = None,
) -> dict:
    """
    Calls the /api/generate endpoint of in Ollama in json mode so it always return a json

    args:
    - prompt (str)
    - system_prompt (str, optional): Custom system prompt to be used instead of the default. If not provided, just the BASE_SYSTEM_PROMPT will be used.
    - context (str, optional): context that has been accumulated from all previous interactions to include in the prompt. Defaults to None.
    - raw_html (str, optional): Raw HTML of the current page to include in the prompt. Defaults to None.
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.
    returns:
    - response (dict/json)

    for reference, example ollama response structure:
    {
    "model": "llama3.2:1b",
    "created_at": "2026-03-26T19:13:47.016445677Z",
    "response": "{"reponse": "YO", ....}",
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
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    # build prompt
    prompt = "### USER PROMPT ###\n" + prompt

    # add context to prompt
    if context:
        prompt = prompt + "\n\n" "### CURRENT ACCUMULATED CONTEXT ###\n" + context

    # add clean raw html to prompt
    if raw_html and raw_html.strip():
        # use crawl4ai to get markdown version of cleaned page
        clean_html = await clean_dom(raw_html)

        # use llm to further extract useful info
        clean_html = await get_llm_response_str(
            system_prompt=SYSTEM_PROMPT_PROCESS_CLEANED_DOM, prompt=clean_html
        )

        # print("Debug: cleaned html extracted useful info:", clean_html)

        prompt = (
            prompt + "\n\n" "### CURRENT USER WEBPAGE INFORMATION ###\n" + clean_html
        )

    # build payload for Ollama API
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

    # extract response and return json
    try:
        response_json = response.json()
        llm_response_str = response_json.get("response", "")
        llm_response_json = json.loads(llm_response_str)
        return llm_response_json
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse Ollama response as JSON: {e}") from e


async def get_llm_response_str(
    prompt: str, system_prompt: str, images_b64: list[str] | None = None
) -> str:
    """
    simply gets a text response from LLM

    used for summarization or other tasks internally. should not be exposed as an endpoint.
    use the json version get_llm_response_json() for ALL communication between the API and extension for consistent communication protocal.
    since this is for internal use, it will not use the default system prompt.

    args:
    - prompt (str)
    - system_prompt (str): system prompt.
    - images_b64 (list of str, optional): list of base64-encoded images to include in the prompt. Defaults to None.

        returns:
    - response (str)

    """

    if not system_prompt or not system_prompt.strip():
        raise ValueError("system_prompt must be a non-empty string")

    payload = {
        "model": MODEL_NAME,
        "system": system_prompt,
        "prompt": prompt,
        "images": images_b64 or [],
        "stream": False,
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

    # extract response and return as string
    try:
        response_json = response.json()
        llm_response_str = response_json.get("response", "")
        return llm_response_str
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"Failed to parse Ollama response as JSON: {e}") from e


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

    context = """
        current_medications: Lisinopril,Metformin
    """
    image_path = "tests/test_report.png"

    with open("tests/testpage1.html", "r", encoding="utf-8") as f:
        raw_html = f.read()

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    import base64

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = asyncio.run(
        get_llm_response_json(
            prompt=prompt,
            context=context,
            images_b64=[image_b64],
            system_prompt=CHAT_SYSTEM_PROMPT,
            raw_html=raw_html,
        )
    )

    print(json.dumps(response, indent=2))
