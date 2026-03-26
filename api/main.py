"""
Main API server for handling requests
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from routes.generate import router as generate_router
from routes.health import router as health_router

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
app.include_router(generate_router)
