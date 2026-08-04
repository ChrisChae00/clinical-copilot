import logging

import httpx
from auth import require_api_key
from config import (
    WHISPERX_API_KEY,
    WHISPERX_CF_ACCESS_CLIENT_ID,
    WHISPERX_CF_ACCESS_CLIENT_SECRET,
    WHISPERX_TIMEOUT,
    WHISPERX_URL,
)
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _audio_suffix(filename: str, content_type: str) -> str:
    media_type = content_type.split(";", 1)[0].strip().lower()
    lower_name = filename.lower()

    if media_type in {"audio/webm", "video/webm"}:
        return ".webm"

    if media_type in {
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/vnd.wave",
    }:
        return ".wav"

    if lower_name.endswith(".webm"):
        return ".webm"

    if lower_name.endswith(".wav"):
        return ".wav"

    raise HTTPException(
        status_code=415,
        detail="Only WebM and WAV audio are supported",
    )


@router.post(
    "/transcribe",
    dependencies=[Depends(require_api_key)],
)
async def transcribe(
    audio: UploadFile = File(...),
) -> dict:
    if not WHISPERX_URL or not WHISPERX_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Transcription service is not configured",
        )

    filename = audio.filename or "audio"
    content_type = audio.content_type or "application/octet-stream"
    suffix = _audio_suffix(filename, content_type)

    if filename == "audio":
        filename = f"audio{suffix}"

    try:
        data = await audio.read(MAX_AUDIO_BYTES + 1)
    finally:
        await audio.close()

    if not data:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds 25 MB limit",
        )

    files = {
        "audio": (
            filename,
            data,
            content_type,
        )
    }

    headers = {
        "CF-Access-Client-Id": WHISPERX_CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": WHISPERX_CF_ACCESS_CLIENT_SECRET,
        "x-api-key": WHISPERX_API_KEY,
    }

    timeout = httpx.Timeout(
        connect=10.0,
        read=WHISPERX_TIMEOUT,
        write=WHISPERX_TIMEOUT,
        pool=10.0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{WHISPERX_URL.rstrip('/')}/transcribe",
                files=files,
                headers=headers,
            )

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Transcription service timed out",
        ) from exc

    except httpx.RequestError as exc:
        logger.warning(
            "Could not reach transcription service: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Transcription service unavailable",
        ) from exc

    if response.status_code in {400, 413, 415}:
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None

        if not isinstance(detail, str):
            detail = "Invalid audio upload"

        raise HTTPException(
            status_code=response.status_code,
            detail=detail,
        )

    if response.status_code != 200:
        logger.error(
            "Transcription service returned status %s",
            response.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail="Transcription service failed",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Transcription service returned invalid JSON",
        ) from exc

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("segments"), list)
        or not isinstance(payload.get("language"), str)
    ):
        raise HTTPException(
            status_code=502,
            detail="Transcription service returned an invalid response",
        )

    return payload
