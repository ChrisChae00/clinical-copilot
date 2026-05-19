# API server
Serves as the backend API server that interfaces with the LLM (Ollama) and future Speech-to-Text services.

Built with FastAPI.

## Routes
- GET `/health`: checks if the Ollama server is running.
- POST `/generate-str`: takes a prompt and optional context, returns a generated string from the model.
- POST `/generate-json`: takes a prompt and returns generated JSON from the model using JSON mode.
- POST `/process-context`: takes the current page HTML and existing accumulated context, returns an updated combined context object.
- POST `/autofill`: takes saved context and a list of fields to fill, returns autofill instructions such as text values and selected dropdown options.

> Route details and example request/response formats are defined in `api/routes/xxx.py`.