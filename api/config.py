"""
This module defines the configuration of environment variables for the API.
"""

import os


def _clean_env(name: str) -> str | None:
    """
    Read an env var and strip surrounding whitespace/newlines.

    Guards against values picked up with stray \\r (e.g. a CRLF-terminated
    .env file), which would otherwise silently corrupt URLs and headers.
    """
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


API_KEY = _clean_env("API_KEY")
OLLAMA_URL = _clean_env("OLLAMA_URL")
MODEL_NAME = _clean_env("OLLAMA_MODEL")
MAX_CONTEXT_LEN = int(os.getenv("MAX_CONTEXT_LEN", "8192"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "300"))

OLLAMA_CF_ACCESS_CLIENT_ID = _clean_env("OLLAMA_CF_ACCESS_CLIENT_ID")
OLLAMA_CF_ACCESS_CLIENT_SECRET = _clean_env("OLLAMA_CF_ACCESS_CLIENT_SECRET")
