"""Offline MVP traffic scenarios; these are not live or historical congestion."""

from __future__ import annotations

from typing import Final

from app.models.traffic import TrafficProfile, TrafficProfileId

STANDARD_TRAFFIC_PROFILE_ID: Final[TrafficProfileId] = "standard"
TRAFFIC_PROFILES: Final[dict[TrafficProfileId, TrafficProfile]] = {
    "standard": TrafficProfile(
        profile_id="standard",
        display_name="Обычная загрузка",
        traffic_factor=1.00,
        description="MVP reference scenario; not live traffic.",
    ),
    "moderate": TrafficProfile(
        profile_id="moderate",
        display_name="Умеренная загруженность",
        traffic_factor=1.15,
        description="MVP scenario assumption; not live or historical traffic.",
    ),
    "peak": TrafficProfile(
        profile_id="peak",
        display_name="Пиковая загруженность",
        traffic_factor=1.35,
        description="MVP scenario assumption; not live or historical traffic.",
    ),
}


class TrafficProfileError(ValueError):
    """Raised when a caller asks for an unsupported offline traffic scenario."""


def traffic_profile(profile_id: str) -> TrafficProfile:
    try:
        return TRAFFIC_PROFILES[profile_id]  # type: ignore[index]
    except KeyError as error:
        supported = ", ".join(TRAFFIC_PROFILES)
        raise TrafficProfileError(
            f"Unknown traffic_profile_id {profile_id!r}; supported: {supported}"
        ) from error
