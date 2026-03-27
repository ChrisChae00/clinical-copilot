"""
Main API server for handling requests

example request:

POST http://localhost:8000/generate
Content-Type: application/json
X-API-Key: api-key-placeholder

{
  "prompt": "hi?"
}

"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.generate_json import router as generate_json_router
from routes.generate_str import router as generate_str_router
from routes.health import router as health_router
from routes.process_context import router as process_context_router

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
app.include_router(generate_str_router)
app.include_router(generate_json_router)
app.include_router(process_context_router)
