"""Authenticated conversational endpoint backed by Ollama's native chat API."""

import json
import logging
from typing import Any, Literal

from auth import require_api_key
from dom.dom_processor import clean_dom
from fastapi import APIRouter, Depends, HTTPException
from llm.client import get_llm_chat_response, get_llm_response_json
from llm.prompts import (
    CHAT_SYSTEM_PROMPT,
    CHAT_TOOL_SELECTION_GUIDANCE,
    SYSTEM_PROMPT_EXTRACT_ATTACHMENT_KNOWLEDGE,
)
from llm.tools import (
    ALLOWED_CHAT_TOOL_ARGUMENTS,
    CHAT_TOOLS,
    REQUIRED_CHAT_TOOL_ARGUMENTS,
    SUPPORTED_CHAT_TOOLS,
)
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter()
logger = logging.getLogger(__name__)

MAX_REPLAY_PAGE_CHARS = 16000
CURRENT_PAGE_MARKER = "### CURRENT USER WEBPAGE INFORMATION ###"
HISTORICAL_PAGE_MARKER = "### HISTORICAL WEBPAGE INFORMATION FROM AN EARLIER TURN ###"
ATTACHMENT_KNOWLEDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {"type": "string"},
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


class ChatHistoryMessage(BaseModel):
    """A replay-safe client-owned conversation turn."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str
    images: list[str] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    messages: list[ChatHistoryMessage] = Field(default_factory=list)
    context: str | None = None
    raw_html: str | None = None
    system_prompt: str | None = None
    images_b64: list[str] | None = None


@router.post("/chat", dependencies=[Depends(require_api_key)])
async def chat(request: ChatRequest):
    """Generate the next assistant turn and any native action tool calls."""

    try:
        return await _get_chat_response(
            prompt=request.prompt,
            messages=request.messages,
            context=request.context,
            raw_html=request.raw_html,
            system_prompt=request.system_prompt,
            images_b64=request.images_b64,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


async def _get_chat_response(
    prompt: str,
    messages: list[ChatHistoryMessage | dict[str, Any]] | None = None,
    context: str | None = None,
    raw_html: str | None = None,
    system_prompt: str | None = None,
    images_b64: list[str] | None = None,
) -> dict[str, Any]:
    """Build native messages, call Ollama, and return a replay-safe result."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if system_prompt is not None and (
        not isinstance(system_prompt, str) or not system_prompt.strip()
    ):
        raise ValueError("system_prompt must be a non-empty string when provided")
    if context is not None and not isinstance(context, str):
        raise ValueError("context must be a string when provided")
    if raw_html is not None and not isinstance(raw_html, str):
        raise ValueError("raw_html must be a string when provided")
    if images_b64 is not None and (
        not isinstance(images_b64, list)
        or not all(isinstance(image, str) for image in images_b64)
    ):
        raise ValueError("images_b64 must be a list of strings when provided")

    history = _normalize_client_messages(messages or [])
    # The extension supplies a specialized prompt while reviewing a finalized
    # conversation. Keep the shared tool-selection safety guidance in force for
    # that mode too; a custom presentation prompt must not make action selection
    # more speculative.
    selected_system_prompt = (
        CHAT_SYSTEM_PROMPT
        if system_prompt is None
        else system_prompt.rstrip() + "\n\n" + CHAT_TOOL_SELECTION_GUIDANCE.strip()
    )
    ollama_user_content, replay_user_content = await _build_user_contents(
        prompt=prompt,
        context=context,
        raw_html=raw_html,
    )

    ollama_user_message: dict[str, Any] = {
        "role": "user",
        "content": ollama_user_content,
    }
    replay_user_message: dict[str, Any] = {
        "role": "user",
        "content": replay_user_content,
    }
    if images_b64:
        ollama_user_message["images"] = list(images_b64)
        replay_user_message["images"] = list(images_b64)

    ollama_messages = [
        {"role": "system", "content": selected_system_prompt},
        *[_mark_replayed_page_historical(message) for message in history],
        ollama_user_message,
    ]
    ollama_response = await get_llm_chat_response(
        ollama_messages,
        tools=CHAT_TOOLS,
    )

    updated_context = context or ""
    if images_b64:
        try:
            extracted = await get_llm_response_json(
                prompt=_attachment_extraction_prompt(prompt, len(images_b64)),
                system_prompt=SYSTEM_PROMPT_EXTRACT_ATTACHMENT_KNOWLEDGE,
                images_b64=list(images_b64),
                response_schema=ATTACHMENT_KNOWLEDGE_SCHEMA,
            )
            updated_context = _merge_attachment_knowledge(updated_context, extracted)
        except Exception as exc:
            # Attachment memory improves later turns, but it is auxiliary. A
            # successful primary chat/tool response must not be discarded just
            # because a second extraction response was unavailable or malformed.
            logger.warning("Could not extract durable attachment knowledge: %s", exc)

    raw_assistant_message = ollama_response["message"]
    raw_tool_calls = raw_assistant_message.get("tool_calls") or []
    tool_calls = _normalize_tool_calls(raw_tool_calls)
    actions = _actions_from_tool_calls(tool_calls)
    assistant_content = raw_assistant_message.get("content", "").strip()
    response_text = _safe_response_text(
        assistant_content,
        actions,
    )
    tool_only = bool(tool_calls) and not assistant_content

    assistant_message: dict[str, Any] = {
        "role": "assistant",
        "content": assistant_content,
    }
    if tool_calls:
        assistant_message["tool_calls"] = tool_calls

    # A tool suggestion is deliberately not executed by this endpoint. Do not
    # replay unresolved tool_calls on the next request: Ollama would expect a
    # corresponding role="tool" result. The standalone `message`, `tool_calls`,
    # and `raw_tool_calls` fields still expose them to the confirmation UI.
    replay_assistant_message = {
        "role": "assistant",
        "content": response_text,
    }
    updated_messages = [
        *history,
        replay_user_message,
        replay_assistant_message,
    ]

    return {
        "response": response_text,
        "updated_context": updated_context,
        "actions": actions,
        "message": assistant_message,
        "messages": updated_messages,
        "tool_calls": tool_calls,
        "raw_tool_calls": raw_tool_calls,
        "tool_only": tool_only,
    }


async def _build_user_contents(
    *,
    prompt: str,
    context: str | None,
    raw_html: str | None,
) -> tuple[str, str]:
    ollama_parts = ["### USER PROMPT ###\n", prompt]
    replay_parts = [prompt]

    if context and context.strip():
        ollama_parts.extend(
            [
                "\n\n### CURRENT ACCUMULATED CONTEXT ###\n",
                context,
            ]
        )

    if raw_html and raw_html.strip():
        cleaned_page = await clean_dom(raw_html)
        page_section = [
            f"\n\n{CURRENT_PAGE_MARKER}\n",
            cleaned_page,
        ]
        ollama_parts.extend(page_section)
        # Page information is turn-specific and must survive in chat history.
        # Stable clinical context is supplied separately on each request and is
        # intentionally not duplicated into every replayed user turn.
        replay_page = cleaned_page
        if len(replay_page) > MAX_REPLAY_PAGE_CHARS:
            replay_page = (
                replay_page[:MAX_REPLAY_PAGE_CHARS]
                + "\n[Older page detail truncated for chat history.]"
            )
        replay_parts.extend(
            [
                "\n\n### CURRENT USER WEBPAGE INFORMATION ###\n",
                replay_page,
            ]
        )

    return "".join(ollama_parts), "".join(replay_parts)


def _mark_replayed_page_historical(message: dict[str, Any]) -> dict[str, Any]:
    """Prevent an earlier page snapshot from masquerading as the current page."""

    content = message.get("content", "")
    if CURRENT_PAGE_MARKER not in content:
        return message
    return {
        **message,
        "content": content.replace(CURRENT_PAGE_MARKER, HISTORICAL_PAGE_MARKER),
    }


def _attachment_extraction_prompt(user_prompt: str, image_count: int) -> str:
    noun = "image" if image_count == 1 else "images"
    return (
        f"Extract durable facts from the {image_count} attached {noun}.\n\n"
        "The images were attached to this user message (use it only as context for "
        "understanding the documents):\n"
        f"{user_prompt}"
    )


def _merge_attachment_knowledge(
    context: str,
    extraction: dict[str, Any],
) -> str:
    """Append unique, validated image facts to the client-owned session context."""

    facts = extraction.get("facts")
    if not isinstance(facts, list):
        raise RuntimeError("Attachment extraction response must contain a 'facts' list")

    existing_facts = {
        " ".join(line.removeprefix("-").casefold().split())
        for line in context.splitlines()
        if line.strip()
    }
    new_facts: list[str] = []
    seen: set[str] = set()

    for fact in facts:
        if not isinstance(fact, str):
            continue
        cleaned = " ".join(fact.split())
        normalized = cleaned.casefold()
        if not cleaned or normalized in seen or normalized in existing_facts:
            continue
        seen.add(normalized)
        new_facts.append(cleaned)

    if not new_facts:
        return context

    knowledge = "### KNOWLEDGE EXTRACTED FROM ATTACHMENTS ###\n" + "\n".join(
        f"- {fact}" for fact in new_facts
    )
    return "\n\n".join(part for part in (context.strip(), knowledge) if part)


def _normalize_client_messages(
    messages: list[ChatHistoryMessage | dict[str, Any]],
) -> list[dict[str, Any]]:
    """Accept only replay-safe user/assistant history from the client."""

    if not isinstance(messages, list):
        raise ValueError("messages must be a list")

    normalized: list[dict[str, Any]] = []
    allowed_keys = {"role", "content", "images"}

    for index, message in enumerate(messages):
        if isinstance(message, ChatHistoryMessage):
            role = message.role
            content = message.content
            images = message.images
        elif isinstance(message, dict):
            unexpected_keys = set(message) - allowed_keys
            if unexpected_keys:
                unexpected = ", ".join(sorted(unexpected_keys))
                raise ValueError(f"messages[{index}] contains unsupported fields: {unexpected}")
            role = message.get("role")
            content = message.get("content")
            images = message.get("images")
        else:
            raise ValueError(f"messages[{index}] must be a JSON object")

        if role not in {"user", "assistant"}:
            raise ValueError(
                f"messages[{index}].role must be 'user' or 'assistant'; "
                "client system/tool messages are not allowed"
            )
        if not isinstance(content, str):
            raise ValueError(f"messages[{index}].content must be a string")
        if images is not None:
            if role != "user":
                raise ValueError(f"messages[{index}].images is only valid for user messages")
            if not isinstance(images, list) or not all(
                isinstance(image, str) for image in images
            ):
                raise ValueError(f"messages[{index}].images must be a list of strings")

        item: dict[str, Any] = {"role": role, "content": content}
        if images:
            item["images"] = list(images)
        normalized.append(item)

    return normalized


def _normalize_tool_calls(tool_calls: object) -> list[dict[str, Any]]:
    """Normalize supported Ollama calls while retaining the raw calls separately."""

    if not isinstance(tool_calls, list):
        return []

    normalized: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue

        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue

        raw_name = function.get("name")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip().lower()
        if name not in SUPPORTED_CHAT_TOOLS:
            continue

        arguments = _normalize_tool_arguments(function.get("arguments"))
        arguments = {
            key: value
            for key, value in arguments.items()
            if key in ALLOWED_CHAT_TOOL_ARGUMENTS[name]
        }
        if "instructions" in arguments:
            instructions = arguments["instructions"]
            if isinstance(instructions, str) and instructions.strip():
                arguments["instructions"] = instructions.strip()
            else:
                arguments.pop("instructions")
        if not REQUIRED_CHAT_TOOL_ARGUMENTS[name].issubset(arguments):
            # Ollama models can occasionally emit a call that violates the
            # advertised JSON schema. Do not surface an unusable action card.
            continue
        normalized_function: dict[str, Any] = {
            "name": name,
            "arguments": arguments,
        }
        function_index = function.get("index")
        if isinstance(function_index, int) and not isinstance(function_index, bool):
            normalized_function["index"] = function_index

        normalized_call: dict[str, Any] = {
            "type": "function",
            "function": normalized_function,
        }

        call_id = tool_call.get("id")
        if isinstance(call_id, str) and call_id:
            normalized_call["id"] = call_id

        normalized.append(normalized_call)

    return normalized


def _normalize_tool_arguments(arguments: object) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _actions_from_tool_calls(tool_calls: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for tool_call in tool_calls:
        name = tool_call["function"]["name"]
        if name not in actions:
            actions.append(name)
    return actions


def _safe_response_text(content: object, actions: list[str]) -> str:
    if isinstance(content, str) and content.strip():
        return content.strip()

    if actions:
        return (
            "I prepared the requested action for your review. "
            "Use the suggestion below when you are ready."
        )

    return "I could not generate a response. Please try again."
