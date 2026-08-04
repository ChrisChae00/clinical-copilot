import asyncio
import logging
import os
import secrets
import tempfile

import whisperx
from config import (
    HF_TOKEN,
    WHISPERX_API_KEY,
    WHISPERX_BATCH_SIZE,
    WHISPERX_DIARIZE,
    WHISPERX_HOST,
    WHISPERX_LANGUAGE,
    WHISPERX_MODEL,
    WHISPERX_PORT,
)
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 25 * 1024 * 1024

app = FastAPI(title="Ally WhisperX Service")

api_key_header = APIKeyHeader(
    name="x-api-key",
    auto_error=False,
)

_whisperx_model = None
_align_models: dict[str, tuple[object, object]] = {}
_diarize_model = None
_device: str | None = None

_inference_lock = asyncio.Lock()


async def require_service_api_key(
    api_key: str | None = Depends(api_key_header),
) -> None:
    if api_key is None or not secrets.compare_digest(
        api_key,
        WHISPERX_API_KEY,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )


def _get_device() -> str:
    global _device

    if _device is None:
        import torch

        _device = "cuda" if torch.cuda.is_available() else "cpu"

    return _device


def _get_whisperx_model():
    global _whisperx_model

    if _whisperx_model is None:
        device = _get_device()
        compute_type = "float16" if device == "cuda" else "int8"

        _whisperx_model = whisperx.load_model(
            WHISPERX_MODEL,
            device,
            compute_type=compute_type,
        )

    return _whisperx_model


def _get_diarize_model():
    global _diarize_model

    if not WHISPERX_DIARIZE or not HF_TOKEN:
        return None

    if _diarize_model is None:
        from whisperx.diarize import DiarizationPipeline

        _diarize_model = DiarizationPipeline(
            token=HF_TOKEN,
            device=_get_device(),
        )

    return _diarize_model


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


def _run_transcription(audio_path: str) -> dict:
    device = _get_device()
    audio_data = whisperx.load_audio(audio_path)

    result = _get_whisperx_model().transcribe(
        audio_data,
        batch_size=WHISPERX_BATCH_SIZE,
        language=WHISPERX_LANGUAGE,
    )

    language = str(result.get("language") or WHISPERX_LANGUAGE)
    transcript_segments = result.get("segments", [])

    if not transcript_segments:
        return {
            "segments": [],
            "language": language,
        }

    if language not in _align_models:
        _align_models[language] = whisperx.load_align_model(
            language_code=language,
            device=device,
        )

    align_model, metadata = _align_models[language]

    result = whisperx.align(
        transcript_segments,
        align_model,
        metadata,
        audio_data,
        device,
        return_char_alignments=False,
    )

    try:
        diarize_model = _get_diarize_model()

        if diarize_model is not None:
            from whisperx.diarize import assign_word_speakers

            diarize_segments = diarize_model(
                audio_data,
                num_speakers=2,
            )

            result = assign_word_speakers(
                diarize_segments,
                result,
            )

    except Exception:
        logger.warning(
            "Diarization unavailable, returning unlabeled segments",
            exc_info=True,
        )

    segments = [
        {
            "speaker": str(segment.get("speaker") or "SPEAKER_00"),
            "text": str(segment.get("text") or "").strip(),
            "start": round(
                float(segment.get("start") or 0.0),
                2,
            ),
            "end": round(
                float(segment.get("end") or 0.0),
                2,
            ),
        }
        for segment in result.get("segments", [])
        if str(segment.get("text") or "").strip()
    ]

    return {
        "segments": segments,
        "language": language,
    }


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post(
    "/transcribe",
    dependencies=[Depends(require_service_api_key)],
)
async def transcribe(
    audio: UploadFile = File(...),
) -> dict:
    filename = audio.filename or "audio"
    content_type = audio.content_type or "application/octet-stream"

    try:
        suffix = _audio_suffix(
            filename,
            content_type,
        )
        data = await audio.read(MAX_AUDIO_BYTES + 1)
    finally:
        await audio.close()

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Audio file is empty",
        )

    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file exceeds 25 MB limit",
        )

    temporary_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        ) as temporary_file:
            temporary_file.write(data)
            temporary_path = temporary_file.name

        async with _inference_lock:
            return await asyncio.to_thread(
                _run_transcription,
                temporary_path,
            )

    except Exception as exc:
        logger.exception("Transcription failed")

        raise HTTPException(
            status_code=500,
            detail="Transcription failed",
        ) from exc

    finally:
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=WHISPERX_HOST,
        port=WHISPERX_PORT,
    )
