"""
Authentication for the API

"""

from config import API_KEY
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def require_api_key(api_key=Depends(api_key_header)):
    """
    Dependency for routes to require API key in the header

    must have X-API-Key: <key> in the request header, where <key> matches the API_KEY in docker-compose.yml env vars
    """
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
