"""Deterministic, network-free Haversine fallback for route planning inputs."""

from __future__ import annotations

import math
from collections.abc import Iterable

from app.core.geo_config import (
    AVERAGE_SPEED_KMPH,
    EARTH_RADIUS_KM,
    ROAD_DISTANCE_FACTOR,
)
from app.core.routing_config import routing_config
from app.core.traffic_config import STANDARD_TRAFFIC_PROFILE_ID, traffic_profile
from app.models.geo import Coordinates, GeoCacheEntry, TravelMetric
from app.models.road import RoadCache
from app.services.routing import (
    OsrmHttpRoutingProvider,
    RoutingProvider,
    RoutingUnavailableError,
)


def haversine_distance_km(origin: Coordinates, destination: Coordinates) -> float:
    """Return great-circle distance in kilometres, without a road multiplier."""

    latitude_delta = math.radians(destination.latitude - origin.latitude)
    longitude_delta = math.radians(destination.longitude - origin.longitude)
    latitude_origin = math.radians(origin.latitude)
    latitude_destination = math.radians(destination.latitude)
    haversine_term = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_origin)
        * math.cos(latitude_destination)
        * math.sin(longitude_delta / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(haversine_term))


def fallback_travel_metric(
    origin: GeoCacheEntry,
    destination: GeoCacheEntry,
    traffic_profile_id: str = STANDARD_TRAFFIC_PROFILE_ID,
) -> TravelMetric:
    """Calculate road-factor distance and travel minutes, or honestly report unresolved."""

    profile = traffic_profile(traffic_profile_id)

    if origin.cache_key == destination.cache_key:
        return TravelMetric(
            origin_cache_key=origin.cache_key,
            destination_cache_key=destination.cache_key,
            distance_km=0.0,
            traffic_profile_id=profile.profile_id,
            traffic_factor=profile.traffic_factor,
            base_unrounded_travel_minutes=0.0,
            base_travel_minutes=0,
            travel_minutes=0,
            method="haversine_fallback",
            routing_source="fallback",
            geometry=None,
            warning=None,
        )
    if origin.coordinates is None or destination.coordinates is None:
        return TravelMetric(
            origin_cache_key=origin.cache_key,
            destination_cache_key=destination.cache_key,
            distance_km=None,
            traffic_profile_id=profile.profile_id,
            traffic_factor=profile.traffic_factor,
            base_unrounded_travel_minutes=None,
            base_travel_minutes=None,
            travel_minutes=None,
            method="unresolved",
            routing_source="unresolved",
            geometry=None,
            warning="At least one geo-cache entry is unresolved.",
        )
    distance_km = haversine_distance_km(origin.coordinates, destination.coordinates)
    road_distance_km = distance_km * ROAD_DISTANCE_FACTOR
    base_unrounded_travel_minutes = road_distance_km / AVERAGE_SPEED_KMPH * 60
    base_travel_minutes = math.ceil(base_unrounded_travel_minutes)
    travel_minutes = math.ceil(base_unrounded_travel_minutes * profile.traffic_factor)
    return TravelMetric(
        origin_cache_key=origin.cache_key,
        destination_cache_key=destination.cache_key,
        distance_km=road_distance_km,
        traffic_profile_id=profile.profile_id,
        traffic_factor=profile.traffic_factor,
        base_unrounded_travel_minutes=base_unrounded_travel_minutes,
        base_travel_minutes=base_travel_minutes,
        travel_minutes=travel_minutes,
        method="haversine_fallback",
        routing_source="fallback",
        geometry=None,
        warning=None,
    )


def travel_metric(
    origin: GeoCacheEntry,
    destination: GeoCacheEntry,
    transport: str,
    road_cache: RoadCache | None = None,
    traffic_profile_id: str = STANDARD_TRAFFIC_PROFILE_ID,
    routing_mode: str | None = None,
    provider: RoutingProvider | None = None,
) -> TravelMetric:
    """Return the one offline travel contract used by every planner.

    Road entries are consumed only from the local cache built by an explicit
    script. This function deliberately has no HTTP client and never attempts
    to fill a cache miss at runtime.
    """
    profile = traffic_profile(traffic_profile_id)
    config = routing_config() if routing_mode is None else None
    routing_mode = routing_mode or config.mode
    if (
        transport == "car"
        and routing_mode != "fallback_only"
        and road_cache is not None
    ):
        entry = road_cache.lookup(origin.cache_key, destination.cache_key)
        if (
            entry is not None
            and entry.distance_km is not None
            and entry.base_duration_min is not None
        ):
            return TravelMetric(
                origin_cache_key=origin.cache_key,
                destination_cache_key=destination.cache_key,
                distance_km=entry.distance_km,
                traffic_profile_id=profile.profile_id,
                traffic_factor=profile.traffic_factor,
                base_unrounded_travel_minutes=float(entry.base_duration_min),
                base_travel_minutes=entry.base_duration_min,
                travel_minutes=math.ceil(
                    entry.base_duration_min * profile.traffic_factor
                ),
                method="road_cache",
                routing_source="road",
                geometry=entry.geometry.coordinates if entry.geometry else None,
                warning=entry.warning,
            )
    if transport == "car" and routing_mode != "fallback_only":
        if provider is None and config is not None and config.base_url:
            try:
                provider = OsrmHttpRoutingProvider(config.base_url)
            except RoutingUnavailableError:
                provider = None
        if provider is None:
            if routing_mode == "road_required":
                raise RoutingUnavailableError("routing_unavailable")
        else:
            try:
                if origin.coordinates is None or destination.coordinates is None:
                    raise RoutingUnavailableError("routing_unavailable")
                result = provider.get_route(origin.coordinates, destination.coordinates)
                return TravelMetric(
                    origin_cache_key=origin.cache_key,
                    destination_cache_key=destination.cache_key,
                    distance_km=result.distance_km,
                    traffic_profile_id=profile.profile_id,
                    traffic_factor=profile.traffic_factor,
                    base_unrounded_travel_minutes=result.base_duration_seconds / 60,
                    base_travel_minutes=result.base_duration_min,
                    travel_minutes=math.ceil(
                        result.base_duration_seconds / 60 * profile.traffic_factor
                    ),
                    method="road_cache",
                    routing_source="road",
                    geometry=result.geometry.coordinates,
                    warning=None,
                )
            except RoutingUnavailableError:
                if routing_mode == "road_required":
                    raise
    fallback = fallback_travel_metric(origin, destination, profile.profile_id)
    warning = fallback.warning
    if transport == "car" and origin.cache_key != destination.cache_key:
        warning = "Road-cache entry unavailable; deterministic Haversine fallback used."
    return fallback.model_copy(update={"warning": warning})


def fallback_travel_matrix(
    entries: Iterable[GeoCacheEntry],
    traffic_profile_id: str = STANDARD_TRAFFIC_PROFILE_ID,
) -> tuple[TravelMetric, ...]:
    """Build a complete ordered matrix using only local entries and Haversine fallback."""

    ordered_entries = tuple(sorted(entries, key=lambda entry: entry.cache_key))
    return tuple(
        fallback_travel_metric(origin, destination, traffic_profile_id)
        for origin in ordered_entries
        for destination in ordered_entries
    )
