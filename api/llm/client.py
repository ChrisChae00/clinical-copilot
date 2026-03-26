"""
Client that interfaces with the LLM (Ollama)
"""

import httpx
from config import MODEL_NAME, OLLAMA_URL


async def get_llm_response(prompt: str):
    """

    Send a prompt to the Ollama LLM server and return the response.
    calls the /api/generate endpoint of in Ollama
    args:
        prompt (str): The prompt to send to the LLM
    returns:
        json: The un altered response from the LLM
    raises:
        ValueError: If the prompt is invalid
        RuntimeError: If there is an issue communicating with Ollama or if Ollama returns an error

    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    payload = {
        "model": MODEL_NAME,
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

    return response.json()


async def is_ollama_healthy() -> bool:
    """
    Check if Ollama is reachable and responding to requests
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
        return True
    except Exception:
        return False


# for debugging, not needed
if __name__ == "__main__":
    import asyncio

    test_prompt = "hello?"
    result = asyncio.run(get_llm_response(test_prompt))
    print(result)
