"""
This module defines the API endpoint for processing the DOM into context
that can be used by the LLM.

example curl request:
    curl -X POST "http://localhost:8000/process-context" \
        -H "Content-Type: application/json" \
            -H "X-API-Key: your_api_key_here" \
            -d '{

                "html": "<html>...</html>",
                "current-context": { ...json... }
            }'

example response:
    {
        "complete_context": { ...json... }
    }

"""

import json

from auth import require_api_key
from fastapi import APIRouter, Depends, HTTPException, Request
from llm.client import get_llm_response

router = APIRouter()

PROCESS_CONTEXT_PROMPT_TEMPLATE = """### SYSTEM ###
You are a context distillation and maintenance engine for a local EMR copilot.

Your job is to maintain one single COMPLETE context object that represents the most useful accumulated understanding of the chart and workflow state so far.

You will be given:
1. CURRENT_CONTEXT: the complete context accumulated so far
2. HTML: the raw HTML of the current EMR page

You must read both inputs and return ONE COMPLETE UPDATED CONTEXT OBJECT that should fully replace the previous context.

Your output is for machine use in future tasks such as:
- question answering
- chart summarization
- autofill and form completion
- workflow assistance
- drafting
- reasoning over chart information
- decision support
- navigation support
- identifying missing information
- preserving useful context across pages

Your most important goals are:
- preserve useful information
- incorporate newly discovered useful information
- avoid losing important details
- avoid inventing facts
- keep the result organized and machine-usable
- keep the context complete, concise, and reusable

### HARD OUTPUT REQUIREMENTS ###
- Return ONLY valid JSON. Nothing else.
- Return EXACTLY ONE JSON object.
- Do NOT output multiple JSON objects.
- Do NOT use markdown.
- Do NOT use code fences.
- Do NOT include explanations, commentary, notes, apologies, or reasoning.
- Do NOT include any text before or after the JSON object.
- The first character of your response must be {
- The last character of your response must be }
- The returned JSON object is the COMPLETE updated context, not a diff, patch, delta, or partial update.
- Never return instructions, analysis, or a description of what you did.
- Never return a schema description instead of the actual context object.
- Every value in the JSON must itself be valid JSON.
- Do NOT use expressions like 140/90. If a value is not a plain JSON number, encode it as a string.

### CORE BEHAVIOR ###
1. Treat CURRENT_CONTEXT as the existing source of accumulated context.
2. Treat HTML as new evidence that may add, refine, reorganize, or contradict parts of the existing context.
3. Merge intelligently.
4. Preserve useful prior context unless the HTML clearly updates, supersedes, or contradicts it.
5. If the HTML contains useful information not yet present in CURRENT_CONTEXT, include it.
6. If the HTML clearly provides a corrected or newer version of previously stored information, update the context accordingly.
7. If the HTML is unrelated, low-value, empty, mostly chrome, or contains no meaningful new information, preserve the useful existing context rather than degrading it.
8. The result must be self-contained and usable on its own without requiring previous versions.

### INFORMATION HANDLING RULES ###
- Prefer factual extraction over speculation.
- Do not invent facts, names, dates, values, relationships, statuses, or interpretations.
- If something is visible but ambiguous, preserve it in a way that clearly reflects uncertainty rather than pretending certainty.
- If something may be useful later but does not fit a neat structure, keep it in a reasonable place in the context instead of dropping it.
- Preserve important narrative clinical content when structure is unclear.
- Prefer retaining meaning over forcing rigid structure.
- Consolidate repeated information when appropriate.
- Deduplicate when appropriate, but do not collapse distinct events just because they appear similar.
- Preserve distinctions such as historical vs current, active vs inactive, pending vs completed, suspected vs confirmed, draft vs finalized, when visible.
- Preserve temporal information such as dates, times, ordering, and recency when visible and useful.
- Preserve references to follow-up needs, unresolved issues, action items, tasks, and future appointments when visible.
- Preserve useful workflow information when relevant.
- Preserve clinically meaningful free text, especially when summarizing it too aggressively would risk losing important details.

### FLEXIBLE STRUCTURE RULES ###
- The output must be a JSON object, but it does NOT need to follow a rigid predefined schema.
- Choose whatever keys, nesting, and organization best preserve useful information for future machine use.
- You may keep the existing structure from CURRENT_CONTEXT if it remains useful.
- You may reorganize the structure if doing so better preserves clarity, meaning, and future usefulness.
- You may introduce new keys whenever needed.
- Do not force all information into a fixed schema if that would lose meaning.
- Prefer stable organization when possible, but completeness and fidelity are more important than rigid uniformity.
- Prefer machine-usable structure where natural, but preserve important raw or semi-structured text when needed.

### PRIORITIZATION RULES ###
Prioritize information that is likely to be useful for future chart-related or workflow-related tasks, including but not limited to:
- patient identity and demographics
- chart or encounter summaries
- diagnoses, concerns, and problem lists
- allergies and intolerances
- medications and treatment-related information
- notes, assessments, plans, and referrals
- appointments, follow-ups, and consultations
- labs, imaging, measurements, and vitals
- forms, documents, correspondence, and reports
- social, family, medical, and surgical history
- care-team, contacts, and provider relationships
- risk factors, preventive care, and reminders
- workflow state and page-specific clues that may matter later

Do not over-prioritize only common categories. Unexpected details may still be important and should be preserved if useful.

### HTML-SPECIFIC RULES ###
The HTML may contain:
- scripts
- styles
- navigation
- repeated labels
- menus
- hidden elements
- page furniture
- browser-like chrome
- extension UI
- duplicated text
- formatting artifacts
- boilerplate content
- machine-generated clutter

Focus on chart-relevant, patient-relevant, document-relevant, and workflow-relevant content.
Ignore obvious non-content clutter unless it carries meaningful state.
Do not copy large irrelevant blocks of boilerplate just because they are present.
Do not preserve script contents, CSS, markup structure, or UI furniture unless they carry genuinely useful operational meaning.

### CURRENT_CONTEXT-SPECIFIC RULES ###
- CURRENT_CONTEXT may already contain useful accumulated knowledge from earlier pages.
- Do not discard useful prior information simply because it is not present in the current HTML.
- Absence in the current HTML is NOT by itself evidence that prior information is false or should be removed.
- Remove or overwrite prior information only when the new HTML clearly indicates it is outdated, incorrect, replaced, contradicted, or no longer applicable.
- If the new HTML adds detail to an existing item, enrich that item rather than duplicating it when appropriate.
- If multiple possibilities cannot be confidently resolved, preserve them in a structured or clearly labeled way.

### CONSERVATIVE INFERENCE RULES ###
You may normalize and organize clearly expressed information.
You may make light transformations that preserve the original meaning, such as:
- cleaning text
- consolidating duplicates
- grouping related facts
- separating repeated entities into arrays
- preserving dates, statuses, labels, and raw excerpts

Do NOT make speculative clinical judgments.
Do NOT infer hidden diagnoses, intentions, causality, or decisions unless directly supported by the input.
Do NOT assume missing values.
Do NOT silently upgrade uncertain information into certain facts.

### QUALITY RULES ###
The updated context should be:
- accurate
- grounded
- complete enough to be useful later
- concise but not lossy
- internally coherent
- machine-usable
- robust to future reuse

Avoid these failure modes:
- dropping useful old information without justification
- copying irrelevant page clutter into the context
- over-summarizing and losing important details
- over-structuring ambiguous information
- under-structuring clearly structured information
- duplicating the same facts repeatedly
- replacing the full context with only the newest page summary
- returning prose instead of JSON
- returning malformed JSON

### FINAL INSTRUCTION ###
Return exactly one valid JSON object representing the COMPLETE UPDATED CONTEXT derived from CURRENT_CONTEXT and HTML.

### INPUT ###
CURRENT_CONTEXT:
{{CURRENT_CONTEXT}}

HTML:
{{HTML}}
"""

JSON_REPAIR_PROMPT_TEMPLATE = """Fix the following JSON so that it is valid.

Rules:
- Return ONLY valid JSON. Nothing else.
- Return EXACTLY ONE JSON object
- Do NOT output multiple JSON objects
- Do NOT use markdown
- Do NOT use code fences
- Do NOT include any explanation or extra text
- The first character must be {
- The last character must be }
- Every value must be valid JSON
- If a value is not a plain number, encode it as a string
- Expressions like 140/90 are invalid JSON and must be strings like "140/90"

Invalid JSON:
{{INVALID_RESPONSE}}
"""


def build_process_context_prompt(html: str, current_context) -> str:
    """
    Helper function that builds the main prompt for the context-processing LLM call.

    Outputs the full prompt string to send to the LLM, including instructions and formatting.

    """
    current_context_json = (
        json.dumps(current_context, ensure_ascii=False, indent=2)
        if current_context is not None
        else "null"
    )

    prompt = PROCESS_CONTEXT_PROMPT_TEMPLATE
    prompt = prompt.replace("{{CURRENT_CONTEXT}}", current_context_json)
    prompt = prompt.replace("{{HTML}}", html)
    # print(prompt)
    return prompt


def build_json_repair_prompt(invalid_response: str) -> str:
    """
    Build a repair prompt if the first LLM response is not valid JSON.
    """
    prompt = JSON_REPAIR_PROMPT_TEMPLATE
    prompt = prompt.replace("{{INVALID_RESPONSE}}", invalid_response)
    return prompt


def extract_ollama_response(ollama_response: dict) -> str:
    """
    Extract the text from Ollama /api/generate response payload.

    response looks like:
    {
    "model": "llama3.2:1b",
    "created_at": "2026-03-26T19:13:47.016445677Z",
    "response": "Yo",
    "done": true,
    "done_reason": "stop",
    "context": [...],
    "total_duration": 21402465413,
    "load_duration": 20995589077,
    "prompt_eval_count": 30,
    "prompt_eval_duration": 2134529,
    "eval_count": 23,
    "eval_duration": 50131658
    }
    """
    if not isinstance(ollama_response, dict):
        raise RuntimeError("Ollama response must be a json object")

    response_text = ollama_response.get("response")

    if not isinstance(response_text, str) or not response_text.strip():
        raise RuntimeError(
            "Ollama response did not contain a non-empty 'response' field"
        )

    return response_text.strip()


def parse_complete_context(response_text: str):

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object")

    return parsed


@router.post("/process-context", dependencies=[Depends(require_api_key)])
async def process_context(request: Request):
    """
    /process-context endpoint that takes a JSON body with:
    - "html": raw HTML of the current page
    - "current-context": the current accumulated context (any JSON value)

    It sends both to the LLM, which returns a complete updated context object.

    example request body:
    {
        "html": "<html>...</html>",
        "current-context": { ...json... }
    }

    example response body:
    {
        "complete_context": { ...json... }
    }

    """
    # receive html and current context
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Request body must be a JSON object"
        )

    html = body.get("html")
    current_context = body.get("current-context", None)

    if not isinstance(html, str) or not html.strip():
        raise HTTPException(
            status_code=400,
            detail="html is required and must be a non-empty string",
        )

    # built proompt
    prompt = build_process_context_prompt(html=html, current_context=current_context)

    # call llm
    try:

        ollama_response = await get_llm_response(prompt)
        llm_response_text = extract_ollama_response(ollama_response)

        # first attempt to parse complete context
        try:
            complete_context = parse_complete_context(llm_response_text)

        # if parsing fails, try with a repair prompt
        except ValueError:
            print("DEBUG: POST /process-context")
            print("Raw LLM response before repair:")
            print(llm_response_text)
            repair_prompt = build_json_repair_prompt(llm_response_text)
            repair_ollama_response = await get_llm_response(repair_prompt)
            repair_response_text = extract_ollama_response(repair_ollama_response)
            print("Raw LLM response after repair:")
            print(repair_response_text)
            complete_context = parse_complete_context(repair_response_text)

    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to process context with LLM: {e}",
        ) from e

    return {"complete_context": complete_context}
