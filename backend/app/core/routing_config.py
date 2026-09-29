"""Explicit routing mode; fallback-only is the safe offline default."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from typing import Literal

RoutingMode = Literal["fallback_only", "road_if_available", "road_required"]


@dataclass(frozen=True)
class RoutingConfig:
    mode: RoutingMode
    base_url: str | None
    interactive_base_url: str | None


def routing_config() -> RoutingConfig:
    mode = getenv("ROUTEFLOW_ROUTING_MODE", "fallback_only")
    if mode not in {"fallback_only", "road_if_available", "road_required"}:
        raise ValueError("ROUTEFLOW_ROUTING_MODE must be fallback_only, road_if_available, or road_required")
    return RoutingConfig(
        mode=mode,
        base_url=getenv("ROUTING_BASE_URL") or None,
        interactive_base_url=getenv("ROUTEFLOW_ROUTE_GEOMETRY_URL") or None,
    )
