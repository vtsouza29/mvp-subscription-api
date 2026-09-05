"""API key authentication for this service's own routes."""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

API_KEY_HEADER = "X-API-Key"

_api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    description="Chave de API do serviço de assinaturas.",
)


async def require_api_key(
    provided_key: str | None = Depends(_api_key_scheme),
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject the request unless it carries the configured API key."""
    if not provided_key or not secrets.compare_digest(provided_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API ausente ou inválida.",
        )
