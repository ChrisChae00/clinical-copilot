"""
Main API server for handling requests

example request:

POST http://localhost:8000/generate-str
Content-Type: application/json
X-API-Key: api-key-placeholder

{
  "prompt": "hi?"
}

"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.analyze_transcript import router as analyze_transcript_router
from routes.autofill import router as autofill_router
from routes.chat import router as chat_router
from routes.draft_action import router as draft_action_router
from routes.health import router as health_router
from routes.transcribe import router as transcribe_router

app = FastAPI(title="Ally API")

# Required
# Without this, browser CORS policy will block the request/response
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# routes
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(autofill_router)
app.include_router(transcribe_router)
app.include_router(analyze_transcript_router)
app.include_router(draft_action_router)
