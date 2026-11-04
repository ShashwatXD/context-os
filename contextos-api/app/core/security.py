"""Security, Authentication and Permission checks for ContextOS."""

from typing import Optional
from fastapi import Header, HTTPException, status
from app.core.config import settings
from app.core.exceptions import PermissionDeniedError


def verify_api_token(authorization: Optional[str] = Header(None)) -> str:
    """Validates the Authorization Bearer token."""
    if not settings.API_TOKEN:
        return "anonymous"

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme. Use 'Bearer <token>'",
        )

    token = parts[1]
    if token != settings.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API token",
        )

    return token


def enforce_tool_permission(agent_permissions: list[str], required_tool: str) -> None:
    """Enforces that an agent has execution rights for a specific tool."""
    if "*" in agent_permissions or required_tool in agent_permissions:
        return
    raise PermissionDeniedError(
        actor="Agent",
        required_permission=f"tool:{required_tool}",
    )

