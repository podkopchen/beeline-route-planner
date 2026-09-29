"""Strict geo-cache and offline fallback travel models for GEO-001."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.normalized_dataset import StrictModel

GeoStatus = Literal["resolved", "unresolved"]
GeoSource = Literal["nominatim", "manual_cache", "synthetic_proxy", "unresolved"]
GeoProvenance = Literal["nominatim", "synthetic_proxy", "legacy_unknown", "unresolved"]
GeoTargetKind = Literal["request", "office", "synthetic_event"]
GeoPrecision = Literal["house", "street", "synthetic_proxy", "legacy_unknown"]
GeoQueryVariant = Literal["raw_freeform", "normalized_freeform", "structured_street"]


class Coordinates(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GeoCacheEntry(StrictModel):
    cache_key: str
    normalized_address: str
    coordinates: Coordinates | None
    source: GeoSource
    geo_source: GeoProvenance | None = None
    status: GeoStatus
    warning: str | None
    query_variant: GeoQueryVariant | None = None
    display_name: str | None = None
    precision: GeoPrecision | None = None
    approximate: bool | None = None
    geocode_attempted: bool = False
    location_source_request_id: str | None = None


class GeoTarget(StrictModel):
    target_id: str
    target_kind: GeoTargetKind
    address: str
    cache_key: str


class GeoDataset(StrictModel):
    entries: tuple[GeoCacheEntry, ...]
    targets: tuple[GeoTarget, ...]


class TravelMetric(StrictModel):
    origin_cache_key: str
    destination_cache_key: str
    distance_km: float | None
    traffic_profile_id: str
    traffic_factor: float
    base_unrounded_travel_minutes: float | None
    base_travel_minutes: int | None
    travel_minutes: int | None
    method: Literal["road_cache", "haversine_fallback", "unresolved"]
    routing_source: Literal["road", "fallback", "unresolved"]
    geometry: tuple[tuple[float, float], ...] | None = None
    warning: str | None
