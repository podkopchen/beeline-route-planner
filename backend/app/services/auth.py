"""Small signed-cookie session service with no external identity dependency."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from app.core.auth_config import AuthConfig

COOKIE_NAME = "routeflow_session"


@dataclass(frozen=True, slots=True)
class AuthUser:
    username: str
    display_name: str
    role: str


def authenticate(username: str, password: str, config: AuthConfig) -> AuthUser | None:
    username_ok = hmac.compare_digest(username.encode(), config.username.encode())
    password_ok = hmac.compare_digest(password.encode(), config.password.encode())
    if not username_ok or not password_ok:
        return None
    return AuthUser(config.username, config.display_name, config.role)


def issue_session(user: AuthUser, config: AuthConfig, now: int | None = None) -> str:
    payload = json.dumps(
        {
            "sub": user.username,
            "name": user.display_name,
            "role": user.role,
            "exp": (now if now is not None else int(time.time()))
            + config.session_ttl_seconds,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = _encode(payload)
    signature = hmac.new(
        config.session_secret.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{_encode(signature)}"


def read_session(
    token: str | None, config: AuthConfig, now: int | None = None
) -> AuthUser | None:
    if not token or "." not in token:
        return None
    encoded, supplied_signature = token.split(".", 1)
    expected = _encode(
        hmac.new(config.session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(supplied_signature, expected):
        return None
    try:
        payload = json.loads(_decode(encoded))
        current = now if now is not None else int(time.time())
        if int(payload["exp"]) <= current or payload["sub"] != config.username:
            return None
        return AuthUser(
            username=str(payload["sub"]),
            display_name=str(payload["name"]),
            role=str(payload["role"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
