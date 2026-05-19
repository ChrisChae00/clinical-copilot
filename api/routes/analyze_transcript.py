"""
POST /analyze-transcript

Analyzes a doctor-patient conversation transcript and returns structured
clinical action items (referrals, lab orders, prescriptions, follow-ups, etc.).

Request body:
{
  "segments": [{"speaker": "SPEAKER_00", "text": "..."}],
  "context": {...}  // optional patient EMR context
}

Response:
{
  "summary": "Visit summary",
  "actions": [
    {
      "type": "referral|lab_order|prescription|follow_up|imaging|note|alert",
      "priority": "high|medium|low",
      "title": "Short title",
      "description": "What to do and why",
      "details": {}
    }
  ]
}
"""

import json
import re

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response_str
from llm.prompts import SYSTEM_PROMPT_ANALYZE_TRANSCRIPT

router = APIRouter()


@router.post("/analyze-transcript", dependencies=[Depends(require_api_key)])
async def analyze_transcript(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from e

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    segments = body.get("segments")
    context = body.get("context")

    if not isinstance(segments, list) or len(segments) == 0:
        raise HTTPException(status_code=400, detail="segments must be a non-empty list")

    prompt = _build_prompt(segments, context)

    try:
        raw = await get_llm_response_str(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_ANALYZE_TRANSCRIPT,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    result = _extract_json(raw)
    if result is None:
        raise HTTPException(status_code=502, detail=f"LLM did not return valid JSON. Raw: {raw!r}")

    return result


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from LLM text output, tolerating surrounding prose."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _build_prompt(segments: list, context: object) -> str:
    transcript_lines = "\n".join(
        f"{seg.get('speaker', 'UNKNOWN')}: {seg.get('text', '')}"
        for seg in segments
    )

    parts = [
        "Analyze this doctor-patient conversation and return the JSON action plan.\n\n",
        "### TRANSCRIPT ###\n",
        transcript_lines,
    ]

    if context:
        parts.append("\n\n### PATIENT CONTEXT ###\n")
        parts.append(json.dumps(context, ensure_ascii=False, indent=2))

    return "".join(parts)
