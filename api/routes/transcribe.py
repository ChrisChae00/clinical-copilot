import logging
import os
import tempfile
from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB

_whisperx_model = None
_align_models: dict = {}  # lang -> (model, metadata)
_diarize_model = None
_device: str | None = None


def _cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def _get_device() -> str:
    global _device
    if _device is None:
        _device = "cuda" if _cuda_available() else "cpu"
    return _device


def _get_whisperx_model():
    global _whisperx_model
    if _whisperx_model is None:
        import whisperx
        device = _get_device()
        compute_type = "float16" if device == "cuda" else "int8"
        _whisperx_model = whisperx.load_model("base", device, compute_type=compute_type)
    return _whisperx_model


def _get_diarize_model():
    global _diarize_model
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return None
    if _diarize_model is None:
        from whisperx.diarize import DiarizationPipeline
        _diarize_model = DiarizationPipeline(
            token=hf_token, device=_get_device()
        )
    return _diarize_model


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Accepts a WebM or WAV audio upload (max 25 MB) and returns diarized transcript segments."""
    content_type = audio.content_type or ""
    suffix = ".webm" if "webm" in content_type else ".wav"

    tmp_path = None
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB limit")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        import whisperx

        model = _get_whisperx_model()
        device = _get_device()

        result = model.transcribe(tmp_path, batch_size=4, language="en")
        lang = "en"

        if lang not in _align_models:
            align_model, metadata = whisperx.load_align_model(
                language_code=lang, device=device
            )
            _align_models[lang] = (align_model, metadata)

        align_model, metadata = _align_models[lang]
        result = whisperx.align(
            result["segments"],
            align_model,
            metadata,
            tmp_path,
            device,
            return_char_alignments=False,
        )

        diarize_model = _get_diarize_model()
        if diarize_model is not None:
            from whisperx.diarize import assign_word_speakers
            diarize_segments = diarize_model(tmp_path, num_speakers=2)
            result = assign_word_speakers(diarize_segments, result)

        segments = [
            {
                "speaker": seg.get("speaker", "SPEAKER_00"),
                "text": seg["text"].strip(),
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
            }
            for seg in result["segments"]
            if seg.get("text", "").strip()
        ]

        return {"segments": segments, "language": lang}

    except Exception:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail="Transcription failed")

    finally:
        if tmp_path:
            os.unlink(tmp_path)
