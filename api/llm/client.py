"""Async client helpers for Ollama's native chat API."""

import json
from typing import Any

import httpx
from config import (
    LLM_TIMEOUT,
    MAX_CONTEXT_LEN,
    MODEL_NAME,
    OLLAMA_CF_ACCESS_CLIENT_ID,
    OLLAMA_CF_ACCESS_CLIENT_SECRET,
    OLLAMA_URL,
)


_OLLAMA_MESSAGE_ROLES = {"system", "user", "assistant", "tool"}


async def get_llm_chat_response(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    response_format: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a non-streaming request to Ollama's ``/api/chat`` endpoint.

    This is the low-level interface used by every LLM-backed feature. Callers
    that need plain text or structured JSON should normally use
    :func:`get_llm_response_str` or :func:`get_llm_response_json` instead.
    """

    if not OLLAMA_URL:
        raise RuntimeError("OLLAMA_URL is not configured")
    if not MODEL_NAME:
        raise RuntimeError("OLLAMA_MODEL is not configured")

    normalized_messages = _normalize_messages(messages)

    payload: dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": normalized_messages,
        "stream": False,
        "think": False,
        "options": {"num_ctx": MAX_CONTEXT_LEN},
    }

    if tools is not None:
        if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
            raise ValueError("tools must be a list of JSON objects")
        payload["tools"] = tools

    if response_format is not None:
        if not isinstance(response_format, (str, dict)):
            raise ValueError("response_format must be 'json' or a JSON schema object")
        payload["format"] = response_format

    try:
        async with httpx.AsyncClient(timeout=_llm_timeout()) as client:
            response = await client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/chat",
                json=payload,
                headers=_ollama_headers(),
            )
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach Ollama: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Ollama returned status code {response.status_code}: {response.text}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {response.text}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Ollama response must be a JSON object")

    message = data.get("message")
    if not isinstance(message, dict):
        raise RuntimeError(f"Ollama response does not contain a valid 'message': {data}")
    if message.get("role") not in {None, "assistant"}:
        raise RuntimeError("Ollama response message role must be 'assistant'")

    tool_calls = message.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, list):
        raise RuntimeError("Ollama assistant message 'tool_calls' must be a list")

    content = message.get("content")
    if content is None and tool_calls:
        # Some tool-capable models omit content instead of returning an empty
        # string for a tool-only turn. Normalize that valid case for callers.
        message = {**message, "content": ""}
        data = {**data, "message": message}
    elif not isinstance(content, str):
        raise RuntimeError("Ollama assistant message does not contain string 'content'")

    return data


async def get_llm_response_str(
    prompt: str,
    system_prompt: str,
    images_b64: list[str] | None = None,
) -> str:
    """Return the assistant text for a single-turn chat request."""

    messages = _single_turn_messages(
        prompt=prompt,
        system_prompt=system_prompt,
        images_b64=images_b64,
    )
    data = await get_llm_chat_response(messages)
    return _assistant_content(data)


async def get_llm_response_json(
    prompt: str,
    system_prompt: str,
    images_b64: list[str] | None = None,
    *,
    response_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a structured JSON object, optionally constrained by a schema."""

    messages = _single_turn_messages(
        prompt=prompt,
        system_prompt=system_prompt,
        images_b64=images_b64,
    )
    data = await get_llm_chat_response(
        messages,
        response_format=response_schema if response_schema is not None else "json",
    )
    content = _assistant_content(data)
    return _parse_json_object(content)


async def is_ollama_healthy() -> bool:
    """Check that Ollama is reachable and the configured model supports tools."""

    if not OLLAMA_URL or not MODEL_NAME:
        return False

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{OLLAMA_URL.rstrip('/')}/api/show",
                json={"model": MODEL_NAME},
                headers=_ollama_headers(),
            )
            response.raise_for_status()
        payload = response.json()
        capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
        if not isinstance(capabilities, list) or "tools" not in capabilities:
            print(
                "WARNING: configured Ollama model does not advertise native tools "
                "capability"
            )
            return False
        return True
    except ValueError as exc:
        print(f"WARNING: Ollama health check returned invalid JSON: {exc}")
        return False
    except httpx.RequestError as exc:
        print(f"WARNING: Ollama health check failed (network): {exc}")
        return False
    except httpx.HTTPStatusError as exc:
        print(
            "WARNING: Ollama health check failed "
            f"(status {exc.response.status_code}): {exc}"
        )
        return False


def _single_turn_messages(
    *,
    prompt: str,
    system_prompt: str,
    images_b64: list[str] | None,
) -> list[dict[str, Any]]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system_prompt must be a non-empty string")

    user_message: dict[str, Any] = {"role": "user", "content": prompt}
    if images_b64:
        user_message["images"] = images_b64

    return [
        {"role": "system", "content": system_prompt},
        user_message,
    ]


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")

    normalized: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise ValueError(f"messages[{index}] must be a JSON object")

        role = message.get("role")
        content = message.get("content")
        if role not in _OLLAMA_MESSAGE_ROLES:
            raise ValueError(f"messages[{index}].role is not supported")
        if not isinstance(content, str):
            raise ValueError(f"messages[{index}].content must be a string")

        item: dict[str, Any] = {"role": role, "content": content}

        images = message.get("images")
        if images is not None:
            if role != "user":
                raise ValueError(f"messages[{index}].images is only valid for user messages")
            if not isinstance(images, list) or not all(
                isinstance(image, str) for image in images
            ):
                raise ValueError(f"messages[{index}].images must be a list of strings")
            if images:
                item["images"] = list(images)

        tool_calls = message.get("tool_calls")
        if tool_calls is not None:
            if role != "assistant" or not isinstance(tool_calls, list):
                raise ValueError(
                    f"messages[{index}].tool_calls is only valid as a list on assistant messages"
                )
            item["tool_calls"] = tool_calls

        thinking = message.get("thinking")
        if thinking is not None:
            if role != "assistant" or not isinstance(thinking, str):
                raise ValueError(
                    f"messages[{index}].thinking is only valid as a string "
                    "on assistant messages"
                )
            item["thinking"] = thinking

        tool_name = message.get("tool_name")
        if role == "tool":
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ValueError(
                    f"messages[{index}].tool_name is required for tool messages"
                )
            item["tool_name"] = tool_name
        elif tool_name is not None:
            raise ValueError(
                f"messages[{index}].tool_name is only valid on tool messages"
            )

        tool_call_id = message.get("tool_call_id")
        if tool_call_id is not None:
            if (
                role != "tool"
                or not isinstance(tool_call_id, str)
                or not tool_call_id.strip()
            ):
                raise ValueError(
                    f"messages[{index}].tool_call_id is only valid as a non-empty "
                    "string on tool messages"
                )
            item["tool_call_id"] = tool_call_id

        normalized.append(item)

    return normalized


def _assistant_content(data: dict[str, Any]) -> str:
    message = data.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("Ollama response does not contain assistant message content")
    return message["content"]


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse one JSON object, optionally wrapped in one Markdown code fence.

    Some models ignore Ollama's structured-output instruction and wrap an
    otherwise valid object in a Markdown fence labelled ``json``. Keep that
    harmless variation from breaking the request, but reject prose, trailing
    data, arrays, and malformed or nested fences. Error messages intentionally
    omit the response content because structured responses can contain sensitive
    clinical information.
    """

    payload = content.strip()
    has_opening_fence = payload.startswith("```")
    has_closing_fence = payload.endswith("```")

    if has_opening_fence or has_closing_fence:
        lines = payload.splitlines()
        opening = lines[0].strip() if lines else ""
        closing = lines[-1].strip() if len(lines) > 1 else ""
        if (
            len(lines) < 3
            or opening.casefold() not in {"```", "```json"}
            or closing != "```"
        ):
            raise RuntimeError(
                "Ollama assistant message contains an invalid JSON code fence; "
                "expected exactly one object in a single ``` or ```json fence"
            )
        payload = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Ollama assistant message does not contain valid JSON "
            f"({exc.msg} at line {exc.lineno}, column {exc.colno})"
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            "Ollama structured response must be a JSON object, "
            f"not {type(parsed).__name__}"
        )

    return parsed


def _llm_timeout() -> httpx.Timeout:
    """Build timeouts suitable for long, non-streaming model generations."""

    return httpx.Timeout(connect=10.0, read=LLM_TIMEOUT, write=30.0, pool=LLM_TIMEOUT)


def _ollama_headers() -> dict[str, str]:
    """Return optional Cloudflare Access headers for the Ollama server."""

    headers: dict[str, str] = {}
    if OLLAMA_CF_ACCESS_CLIENT_ID and OLLAMA_CF_ACCESS_CLIENT_SECRET:
        headers["CF-Access-Client-Id"] = OLLAMA_CF_ACCESS_CLIENT_ID
        headers["CF-Access-Client-Secret"] = OLLAMA_CF_ACCESS_CLIENT_SECRET
    return headers
