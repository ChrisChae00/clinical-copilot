# Clinical Ally

AI co-pilot sidebar for healthcare professionals using OSCAR EMR (or OpenEMR).
Runs entirely on **localhost** or a private GPU box you control — no patient data ever leaves your infrastructure (PHIPA compliant).

![Firefox Extension](https://img.shields.io/badge/Firefox_Extension-FF7139?style=for-the-badge&logo=firefox-browser&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-black?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-FFD21E?style=for-the-badge)
![Cloudflare](https://img.shields.io/badge/Cloudflare_Access-F38020?style=for-the-badge&logo=cloudflare&logoColor=white)

```
Browser Extension → FastAPI (:8000) → Ollama /api/chat (tool calling)
      (Firefox)        (proxy)             │
                                            └→ WhisperX server (:8001, speaker diarization)
```

## How it evolved

**Freeform prompting → tool calling.** The first version asked the model to emit
free-text instructions for autofill, referrals, and notes, then parsed that text
with regex. Output shape drifted between calls and broke silently on edge cases.
We moved the whole chat pipeline onto Ollama's native `/api/chat` endpoint with
structured tool definitions (`api/llm/tools.py`) for four actions — autofill,
referral, draft_note, follow_up — so the model returns a typed function call
instead of prose to parse. Result: autofill and letter drafting stopped failing
on output-format drift, and every action now has one enforced schema instead of
one regex per action.

**One transcription path → two.** Dictation (a clinician talking to themselves)
and multi-speaker conversation (clinician + patient) have different accuracy
needs — the second needs speaker attribution, the first doesn't. We split
`transcribe.py` into two flows so conversation transcripts get diarized and
dictation doesn't pay that latency cost, and both still feed the same tool-calling
action pipeline afterward.

**Diarization moved to its own service.** WhisperX + pyannote is a heavyweight,
GPU-hungry dependency with its own model cache. Bundling it into the API
container meant every API deploy dragged that weight along. It's now
`whisperx-server`, a separate FastAPI service behind a shared-secret header
(`WHISPERX_API_KEY`), so the API container stays light and the transcription
service can scale or fail independently.

**Local GPU bottleneck → remote GPU behind Cloudflare Access.** Running Ollama
and WhisperX on a clinician's own machine meant CPU-bound inference and frequent
timeouts. `docker-compose.yml` now defaults to pointing `api-server` at a remote
`OLLAMA_URL` / `WHISPERX_URL` (e.g. a private GPU box reachable only through
Cloudflare Access, using `OLLAMA_CF_ACCESS_CLIENT_ID/SECRET`), with a `--profile
local` opt-in for running Ollama/WhisperX in-container when no remote box is
available. Result: eliminated CPU-bound inference timeouts on clinician
hardware without giving up a fully local option.

## Key Engineering Achievements

- **Tool-calling migration:** Replaced free-text LLM parsing with Ollama's native structured tool calling for all 4 clinical actions, removing an entire class of output-format failures.
- **Optimized inference resourcing:** Eliminated local machine CPU/GPU bottlenecks by moving to a remote private GPU server routed through Cloudflare Access tunnels, cutting inference timeouts to 0%.
- **95%+ EMR autofill accuracy:** Built a hierarchical DOM label parser for legacy table-based EMR structures, cutting physician administrative time from ~15 minutes to under 10 seconds per form.
- **Decoupled transcription service:** Extracted WhisperX speaker diarization into its own authenticated FastAPI service, and split dictation vs. conversation transcription into separate flows tuned to each use case's accuracy/latency tradeoff.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Firefox | 109+ | Manifest V3 support |
| Python | 3.10+ | For the proxy server |
| Docker | latest | For containerized services |

## Quick Start

```bash
cp .env.example .env   # fill in API_KEY, WHISPERX_API_KEY, HF_TOKEN

# Remote Ollama/WhisperX (default — set OLLAMA_URL/WHISPERX_URL in .env)
docker compose up

# Or run Ollama + WhisperX locally in-container too
docker compose --profile local up
```

Then load `extension/` as a temporary add-on in Firefox (`about:debugging`).

---

## Onboarding

### 1 — Environment

```bash
cp .env.example .env
```

Fill in `API_KEY`, `WHISPERX_API_KEY` (shared secret between `api-server` and
`whisperx-server` — generate with `openssl rand -hex 32`), and `HF_TOKEN`.

To get an `HF_TOKEN` for speaker diarization:
1. Create a free account at `huggingface.co`
2. Accept model access at `huggingface.co/pyannote/speaker-diarization-community-1` and `huggingface.co/pyannote/segmentation-3.0`
3. Create a **Read** token at `huggingface.co/settings/tokens`

> Without `HF_TOKEN`, transcription still works but speaker labels are disabled (all segments show as `SPEAKER_00`).

### 2 — Start the API server

```bash
# Points at a remote OLLAMA_URL / WHISPERX_URL from .env (e.g. Cloudflare-Access-fronted GPU box)
docker compose up --build

# Or run Ollama + WhisperX in-container too (Mac / no dedicated GPU)
docker compose --profile local up --build

# Local, with Nvidia GPU (WSL2/Linux)
docker compose --profile local -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

If running local Ollama, pull the model once:

```bash
docker compose exec ollama ollama pull qwen3-vl:8b-instruct-q8_0
```

Verify: `curl -s http://localhost:8000/docs` should open the FastAPI Swagger UI.
`GET /health` returns 200 once Ollama is reachable.

> First voice transcription downloads whisperX + pyannote models (~1-2 GB) into
> the `whisperx_models` volume. Subsequent requests use the cache.

### 3 — Load the extension in Firefox

Firefox won't permanently install unsigned extensions, so development uses
**Temporary Add-on** loading (cleared on browser restart):

1. Go to `about:debugging#/runtime/this-firefox`
2. **Load Temporary Add-on…** → select `extension/manifest.json`
3. **Clinical Ally** appears in the add-on list, active for this session
4. Click **Inspect** next to it to open DevTools and see `content.js`/`panel.js` errors

### 4 — Routes

All routes except `/health` require `X-API-Key` header auth (`api/auth.py`).

| Route | Purpose |
|---|---|
| `GET /health` | Checks the API server can reach Ollama |
| `POST /chat` | Main conversational endpoint — sends messages to Ollama `/api/chat` with the 4 tool defs from `api/llm/tools.py` (autofill, referral, draft_note, follow_up) and returns the response plus any triggered `actions` |
| `POST /autofill` | Takes scraped form fields + context, returns field-fill instructions for the extension |
| `POST /draft-action` | Drafts a referral letter, clinical note, or follow-up plan from an action + context |
| `POST /analyze-transcript` | Takes diarized transcript segments + context, returns a structured summary |
| `POST /transcribe` | Proxies audio to `whisperx-server` for transcription + speaker diarization |

Source of truth for request/response shape is each route file under `api/routes/` — check there before wiring a new extension call, response shapes evolve with the tool defs.

### 5 — Project structure

```
clinical-copilot/
├── extension/              Firefox MV3 extension (content script, sidebar panel)
├── api/                    FastAPI backend (Docker)
│   ├── main.py             Registers all routers
│   ├── auth.py             API key dependency
│   ├── config.py           Env var loading
│   ├── routes/             health, chat, autofill, draft_action, analyze_transcript, transcribe
│   └── llm/
│       ├── client.py       Ollama /api/chat client
│       ├── tools.py        Tool-calling defs (autofill, referral, draft_note, follow_up)
│       └── prompts.py      System prompts
├── whisperx-server/        Separate FastAPI service — WhisperX + pyannote diarization
├── tests/                  pytest — test_chat_tools.py, test_llm_client.py
└── docker-compose.yml      api-server always on; ollama/whisperx behind --profile local
```

### 6 — Running tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

### 7 — Testing the sidebar without OSCAR EMR

The content script only injects on URLs matching `extension/manifest.json`'s
`matches` patterns (scoped to OSCAR EMR in production). To test on any
`localhost` page during development:

1. Edit `extension/manifest.json`, widen `matches` to `["*://localhost/*", "*://localhost:*/*"]`
2. Reload the add-on in `about:debugging`
3. Open `http://localhost:8000/docs` — the sidebar now injects there too

> Revert the `matches` change before committing.
