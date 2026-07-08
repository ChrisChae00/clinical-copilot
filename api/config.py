"""
This module defines the configuration of environment variables for the API.
"""

import os

API_KEY = os.getenv("API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL")
MODEL_NAME = os.getenv("OLLAMA_MODEL")
MAX_CONTEXT_LEN = int(os.getenv("MAX_CONTEXT_LEN", "8192"))

OLLAMA_CF_ACCESS_CLIENT_ID = os.getenv("OLLAMA_CF_ACCESS_CLIENT_ID")
OLLAMA_CF_ACCESS_CLIENT_SECRET = os.getenv("OLLAMA_CF_ACCESS_CLIENT_SECRET")
