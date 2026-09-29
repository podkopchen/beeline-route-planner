"""Explicit local-only configuration for the read-only API."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class ApiConfig:
    cors_origins: tuple[str, ...]


def api_config() -> ApiConfig:
    raw_origins = getenv(
        "ROUTEFLOW_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return ApiConfig(
        cors_origins=tuple(
            item.strip() for item in raw_origins.split(",") if item.strip()
        )
    )
