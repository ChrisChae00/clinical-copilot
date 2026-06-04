# API Server

Serves as the backend API server for Clinical Ally.

Built with FastAPI.

## Routes

### GET `/health`

Checks whether the API server can reach the Ollama LLM server.

Returns:

```json
{
  "ok": true
}
```

If Ollama is unavailable, the route returns `503`.

---

### POST `/chat`

Takes a user prompt and optional supporting context, page HTML, and images. Returns a structured JSON response from the LLM.

Requires API key authentication.

Request fields:

- `prompt` string, required
- `context` string, optional
- `raw_html` string, optional
- `system_prompt` string, optional
- `images_b64` list of strings, optional

Example request:

```json
{
  "prompt": "What is the patient's name? Summarize the current report.",
  "context": "## patient info ##\npatient_name: John Doe\nage: 45",
  "raw_html": "<html>...</html>",
  "images_b64": ["base64-encoded-image-string"]
}
```

Example response:

```json
{
  "response": "The patient's name is John Doe...",
  "updated_context": "### PATIENT INFORMATION ###\n...",
  "actions": []
}
```

Supported actions may include:

```json
["autofill"]
```

---

### POST `/autofill`

Takes accumulated context, optional user instructions, optional images, and a list of scraped form fields. Returns autofill instructions for the browser extension.

Requires API key authentication.

Request fields:

- `prompt` string, optional
- `context` string, required
- `images_b64` list of strings, optional
- `fields` list of objects, required

Example request:

```json
{
  "prompt": "Fill in reason for visit as: severe headache",
  "context": "## patient info ##\npatient_name: John Doe\nage: 45\ndiagnosis: Hypertension",
  "images_b64": ["base64-encoded-image-string"],
  "fields": [
    {
      "id": "patient_name",
      "label": "Patient Name",
      "type": "text"
    },
    {
      "id": "visit_type",
      "label": "Visit Type",
      "type": "select",
      "options": [
        {
          "value": "routine",
          "label": "Routine Visit"
        },
        {
          "value": "urgent",
          "label": "Urgent Visit"
        }
      ]
    }
  ]
}
```

Example response:

```json
{
  "fills": [
    {
      "field_id": "patient_name",
      "type": "text",
      "value": "John Doe",
      "confidence": 0.99
    },
    {
      "field_id": "visit_type",
      "type": "select",
      "value": "urgent",
      "confidence": 0.85
    }
  ]
}
```

Supported normalized field types:

- `text`
- `textarea`
- `number`
- `date`
- `time`
- `datetime`
- `select`
- `multiselect`
- `checkbox`
- `checkbox_group`
- `radio`
- `contenteditable`
- `combobox`

For selectable fields such as `select`, `radio`, `checkbox_group`, `multiselect`, and `combobox`, the returned value should match one of the provided option values.

## Authentication

Protected routes require an API key header:

```http
X-API-Key: api-key-placeholder
```
> change in dockercompose

## Notes

Route details, request models, and response behavior are defined in:

```text
api/routes/health.py
api/routes/chat.py
api/routes/autofill.py
```

System prompts are defined in:

```text
api/llm/prompts.py
```
