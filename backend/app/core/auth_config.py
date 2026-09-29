"""Local authentication configuration for the dispatcher demo."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class AuthConfig:
    enabled: bool
    username: str
    password: str
    display_name: str
    role: str
    session_secret: str
    session_ttl_seconds: int
    cookie_secure: bool


def auth_config() -> AuthConfig:
    enabled = getenv("ROUTEFLOW_AUTH_ENABLED", "false").lower() in {"1", "true", "yes"}
    secret = getenv("ROUTEFLOW_SESSION_SECRET", "")
    if enabled and len(secret) < 32:
        raise ValueError("ROUTEFLOW_SESSION_SECRET must contain at least 32 characters")
    ttl = int(getenv("ROUTEFLOW_SESSION_TTL_SECONDS", "28800"))
    if ttl < 300:
        raise ValueError("ROUTEFLOW_SESSION_TTL_SECONDS must be at least 300")
    return AuthConfig(
        enabled=enabled,
        username=getenv("ROUTEFLOW_DEMO_USERNAME", "dispatcher"),
        password=getenv("ROUTEFLOW_DEMO_PASSWORD", "RouteFlow2026!"),
        display_name=getenv("ROUTEFLOW_DEMO_DISPLAY_NAME", "Диспетчер смены"),
        role="dispatcher",
        session_secret=secret or "disabled-auth-session-secret-not-used",
        session_ttl_seconds=ttl,
        cookie_secure=getenv("ROUTEFLOW_COOKIE_SECURE", "false").lower()
        in {"1", "true", "yes"},
    )
