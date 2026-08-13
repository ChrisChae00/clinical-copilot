import os

WHISPERX_HOST = os.getenv("WHISPERX_HOST", "127.0.0.1")
WHISPERX_PORT = int(os.getenv("WHISPERX_PORT", "8001"))

WHISPERX_MODEL = os.getenv("WHISPERX_MODEL", "base")
WHISPERX_LANGUAGE = os.getenv("WHISPERX_LANGUAGE", "en")
WHISPERX_BATCH_SIZE = int(os.getenv("WHISPERX_BATCH_SIZE", "4"))
WHISPERX_DIARIZE = os.getenv("WHISPERX_DIARIZE", "true").lower() == "true"

WHISPERX_API_KEY = os.getenv("WHISPERX_API_KEY") or None
HF_TOKEN = os.getenv("HF_TOKEN", "")
