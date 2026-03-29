# Clinical Ally

AI co-pilot sidebar for healthcare professionals using OSCAR EMR (or OpenEMR).
Runs entirely on **localhost** — no patient data ever leaves your machine (PHIPA compliant).

```
Browser Extension → FastAPI (:8000) → Ollama (:11434)
      (Firefox)        (proxy)          (local LLM)
```

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Firefox | 109+ | Manifest V3 support |
| Python | 3.10+ | For the proxy server |
| Ollama | latest | Runs granite4 locally |
| OSCAR EMR | any | Running at `localhost:8080/oscar/` |

---

## Quick Start

### 1 — Start the API server

The API server runs in Docker and includes Ollama.

```bash
docker compose up --build
```

Then pull the model (may take a while):

```bash
docker compose exec ollama ollama pull granite4
```

> **GPU note:** GPU access only works with Docker on WSL2.

Verify: `curl -s http://localhost:8000/docs` should open the FastAPI docs.

### 2 — Load the extension in Firefox

Firefox does not allow installing unsigned extensions permanently in standard mode.
During development, use **Temporary Add-on** loading — the extension stays active until Firefox restarts.

1. In the Firefox address bar, navigate to:
   ```
   about:debugging#/runtime/this-firefox
   ```
2. Click **Load Temporary Add-on…**
3. In the file picker, open this file:
   ```
   extension/manifest.json
   ```
4. **Clinical Ally** appears in the add-on list — it is now active for this Firefox session.

> **Session note:** Temporary add-ons are removed when Firefox closes. Repeat step 2–4 each time you restart the browser.

#### Inspecting the extension

- Click **Inspect** next to Clinical Ally in `about:debugging` to open its DevTools console.
- Any errors from `content.js`, `panel.js`, or failed network requests appear here.

### 3 — Use Clinical Ally

1. Navigate to your OSCAR EMR instance (e.g. `http://localhost:8080/oscar/`)
2. The Clinical Ally sidebar appears as a tab on the right edge of the page.
3. Click it to expand the panel (360 px wide).
4. Type a clinical question in the input field and press **Send** or hit Enter.
5. The AI response appears in the response area within the panel.

> **Sidebar not appearing?** Make sure the URL matches `localhost:8080/oscar/`. The content script only runs on pages matching the manifest's `matches` patterns. See [Testing Without OSCAR EMR](#testing-without-oscar-emr) below.

---

## Testing the Extension

### Verifying the API is reachable

Before testing the sidebar, confirm the API is accepting requests:

```bash
curl -s http://localhost:8000/health
```

Send a test prompt:

```bash
curl -s -X POST http://localhost:8000/generate-str \
  -H "Content-Type: application/json" \
  -H "X-API-Key: api-key-placeholder" \
  -d '{"prompt": "What is hypertension? Reply in one sentence."}' | python3 -m json.tool
```

If you see `503` or `502`, check that the Docker containers are running (`docker compose ps`) and that the model has been pulled.

---

### Testing Without OSCAR EMR

If you don't have OSCAR EMR running locally, you can test the sidebar UI on any `localhost` page in two ways:

**Option A — Widen the content script match (development only)**

Edit `extension/manifest.json` and change the `matches` array:

```json
"matches": ["*://localhost/*", "*://localhost:*/*"]
```

Then reload the extension in `about:debugging` (click **Reload**).
Now the sidebar injects on every `localhost` page, including `http://localhost:8000/docs`.

> Revert this change before committing — the production match should stay scoped to `/oscar/`.

**Option B — Use the FastAPI docs page as a host**

With the proxy running at `http://localhost:8000`, open `http://localhost:8000/docs` in Firefox.
After widening the match (Option A), the Clinical Ally sidebar will appear on this page and you can send test queries end-to-end.

---

### Manual end-to-end checklist

Use this checklist to confirm the full stack is working before running automated tests:

- [ ] `http://localhost:8000/docs` loads the FastAPI Swagger UI
- [ ] `GET /health` returns 200
- [ ] The `POST /generate-str` curl command above returns a response
- [ ] The Clinical Ally add-on appears in `about:debugging` without errors
- [ ] The sidebar tab is visible on the target page
- [ ] Typing a question and pressing **Send** shows a loading indicator
- [ ] A non-empty AI response appears in the panel within ~60 seconds
- [ ] The **Close** button (×) collapses the sidebar

---

## Running Automated Tests

```bash
cd tests
pip install pytest playwright
playwright install firefox
pytest -v
```

> **Note:** Playwright cannot auto-load Firefox extensions. Sprint 1 tests inject `content.js` directly via `page.add_script_tag()`. Full extension loading via `web-ext` is planned for Sprint 2.

---

## Project Structure

```
clinical-copilot/
│
├── extension/                  Firefox MV3 extension
│   ├── manifest.json           Declares permissions, matches, and web-accessible resources
│   ├── content.js              Injected into OSCAR pages — creates the shadow DOM host and iframe
│   ├── panel.html              Sidebar UI markup (runs inside the iframe)
│   ├── panel.css               Sidebar styles, scoped inside shadow DOM
│   └── panel.js                Handles form submit, fetch to API, and response rendering
│
├── api/                        FastAPI backend — bridges extension and LLM (Docker)
│   ├── main.py                 App entrypoint; registers all routes
│   ├── docker-compose.yml      Runs FastAPI + Ollama containers
│   ├── routes/
│   │   ├── health.py           GET /health
│   │   ├── generate_str.py     POST /generate-str — returns plain text response
│   │   ├── generate_json.py    POST /generate-json — returns JSON response
│   │   └── process_context.py  POST /process-context (WIP) — merges DOM + context
│   ├── llm/
│   │   ├── client.py           Ollama API client
│   │   └── prompts.py          System prompts
│   └── auth.py                 API key authentication
│
├── tests/                      Playwright end-to-end tests
│   ├── conftest.py             Firefox browser fixture
│   └── test_sidebar.py         Injects sidebar, submits a question, asserts a response
│
└── docs/
    └── ollama-setup.md         Ollama install and troubleshooting guide (macOS / Linux / Windows)
```

---

## Architecture Notes

- **Shadow DOM** isolates sidebar CSS from EMR page styles
- **Fixed positioning** with `z-index: 2147483647` — sidebar overlays without modifying EMR layout
- **Direct fetch** from content script to proxy — simpler than background script messaging
- **CORS wildcard** — required because `moz-extension://` UUIDs are unpredictable; localhost-only deployment mitigates risk
- **`stream: false`** — synchronous Ollama responses simplify Sprint 1; streaming planned for Sprint 2

---

## Roadmap

| Sprint | Goal |
|---|---|
| Sprint 1 (current) | End-to-end scaffold: sidebar → proxy → Ollama |
| Sprint 2 | Patient context extraction, streaming, closed shadow DOM |
| Sprint 3 | Conversation history, voice input, configurable model |
| Sprint 4 | PHIPA audit log, packaging, deployment guide |
