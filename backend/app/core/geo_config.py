"""Offline-first GEO-001 constants shared by cache and travel calculations."""

from __future__ import annotations

from typing import Final

EARTH_RADIUS_KM: Final = 6371.0088
ROAD_DISTANCE_FACTOR: Final = 1.25
AVERAGE_SPEED_KMPH: Final = 25.0
NOMINATIM_URL: Final = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT: Final = "RouteFlow-Hackathon/0.1 (offline-first geocache builder)"
NOMINATIM_THROTTLE_SECONDS: Final = 1.0
