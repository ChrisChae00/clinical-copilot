"""Native Ollama tools available to the main clinical chat."""

from typing import Any


CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "autofill",
            "description": (
                "Suggest that the user autofill fields on the current page. Call this "
                "when the user asks to enter, add, update, change, populate, complete, "
                "or record information in the current form, even if they do not use the "
                "word autofill. Also call it immediately when the user asks to fill a "
                "page from information already known from conversation context or "
                "attached reports; never ask them to repeat known values. The tool "
                "inspects the current form and safely leaves unsupported fields blank. "
                "Do not call it for questions, summaries, or information the user only "
                "wants remembered. This only presents a confirmation to the user; it "
                "does not modify the page immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": (
                            "A concise description of the information or changes that "
                            "should be applied to the form."
                        ),
                    }
                },
                "required": ["instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "referral",
            "description": (
                "Suggest drafting a referral letter or referral document from the current "
                "patient context. Call this when the user asks to generate, draft, create, "
                "write, or prepare a referral. Do not call it when the user only wants to "
                "fill referral fields on the current page; use autofill for that. Do not "
                "call it for a past/completed referral or a question or general discussion "
                "about referrals. This only presents a confirmation to the user and does "
                "not draft the letter yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": (
                            "A concise description of the requested referral, including "
                            "specialty, reason, or urgency when the user supplied them."
                        ),
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_note",
            "description": (
                "Suggest drafting a clinical visit note from known context. Call this "
                "when the user explicitly asks to draft, write, create, or document a "
                "clinical note. When reviewing a finalized doctor-patient conversation, "
                "you may also call it without an explicit request only when the transcript "
                "contains substantive visit content worth documenting, such as a presenting "
                "concern plus relevant history, findings, assessment, or plan. Do not call "
                "it for greetings, administrative chatter, a short dictation fragment, a "
                "hypothetical discussion, or a transcript with too little clinical content "
                "to support a useful note. This only presents a confirmation and does not "
                "draft the note yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": (
                            "A concise, factual description of the visit content and the "
                            "note to draft. Include the requested note style when supplied."
                        ),
                    }
                },
                "required": ["instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "follow_up",
            "description": (
                "Suggest drafting a follow-up plan or appointment note. Call this only "
                "when the user explicitly requests follow-up, or when a finalized "
                "doctor-patient conversation contains an explicit forward-looking "
                "follow-up commitment or plan. A timeframe counts only when it belongs "
                "to that future plan. Do not infer follow-up merely because it might be "
                "clinically sensible, and do not call it for a past/completed follow-up, "
                "a general recommendation, a question, or an unresolved concern with no "
                "stated future plan. This only presents a confirmation and does not "
                "create the follow-up draft yet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instructions": {
                        "type": "string",
                        "description": (
                            "A concise description of the explicit follow-up plan, including "
                            "timeframe, reason, and monitoring details when stated."
                        ),
                    }
                },
                "required": ["instructions"],
                "additionalProperties": False,
            },
        },
    },
]

CHAT_TOOL_FUNCTIONS = {
    tool["function"]["name"]: tool["function"] for tool in CHAT_TOOLS
}
SUPPORTED_CHAT_TOOLS = frozenset(CHAT_TOOL_FUNCTIONS)
ALLOWED_CHAT_TOOL_ARGUMENTS = {
    name: frozenset(function["parameters"].get("properties", {}))
    for name, function in CHAT_TOOL_FUNCTIONS.items()
}
REQUIRED_CHAT_TOOL_ARGUMENTS = {
    name: frozenset(function["parameters"].get("required", ()))
    for name, function in CHAT_TOOL_FUNCTIONS.items()
}
