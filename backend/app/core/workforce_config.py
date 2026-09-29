"""Deterministic DATA-004 workforce and event configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

WORKFORCE_SEED: Final = 2026
SHIFT_START_HOUR: Final = 10
SHIFT_END_HOUR: Final = 22


@dataclass(frozen=True)
class EngineerTemplate:
    skills: tuple[str, ...]
    available_transport: str
    level: str


ENGINEER_TEMPLATES: Final = (
    EngineerTemplate(("installation",), "car", "senior"),
    EngineerTemplate(("installation", "subscriber_support"), "car", "middle"),
    EngineerTemplate(("installation",), "none", "middle"),
    EngineerTemplate(("installation", "subscriber_support"), "none", "junior"),
    EngineerTemplate(("subscriber_support",), "car", "senior"),
    EngineerTemplate(("subscriber_support",), "car", "middle"),
    EngineerTemplate(("subscriber_support",), "none", "middle"),
    EngineerTemplate(("subscriber_support", "network_repair"), "none", "junior"),
    EngineerTemplate(("network_repair",), "car", "senior"),
    EngineerTemplate(("network_repair",), "car", "middle"),
    EngineerTemplate(("network_repair",), "none", "middle"),
    EngineerTemplate(("network_repair", "installation"), "none", "junior"),
)

ENGINEERS_PER_TERRITORY: Final = {"east": 12, "southeast": 12, "southcenter": 11}
