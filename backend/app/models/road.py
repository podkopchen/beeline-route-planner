"""Read-only, explicitly built OSRM road-routing cache models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.models.normalized_dataset import StrictModel


class GeoJsonLineString(StrictModel):
    """GeoJSON coordinates are longitude/latitude pairs, never generated at runtime."""

    type: Literal["LineString"] = "LineString"
    coordinates: tuple[tuple[Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)], Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]], ...] = Field(min_length=2)


class RoadCacheEntry(StrictModel):
    origin_id: str
    destination_id: str
    origin_cache_key: str
    destination_cache_key: str
    mode: Literal["driving"] = "driving"
    distance_km: float | None = Field(default=None, ge=0)
    base_duration_min: int | None = Field(default=None, ge=0)
    geometry: GeoJsonLineString | None = None
    source: Literal["osrm"] = "osrm"
    created_at: datetime
    status: Literal["resolved", "unresolved"]
    warning: str | None = None


class RoadCache(StrictModel):
    version: int = 1
    entries: tuple[RoadCacheEntry, ...] = ()

    def lookup(
        self, origin_cache_key: str, destination_cache_key: str
    ) -> RoadCacheEntry | None:
        return next(
            (
                item
                for item in self.entries
                if item.origin_cache_key == origin_cache_key
                and item.destination_cache_key == destination_cache_key
                and item.status == "resolved"
            ),
            None,
        )
