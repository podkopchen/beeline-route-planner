"""On-demand road geometry for one published route; planning data stays immutable."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from app.models.geo import Coordinates
from app.services.routing import RoutingProvider, RoutingUnavailableError


@dataclass(frozen=True, slots=True)
class BuiltRoadLeg:
    request_id: str
    sequence: int
    geometry: tuple[tuple[float, float], ...] | None
    source: Literal["cache", "on_demand", "same_location"]


@dataclass(frozen=True, slots=True)
class BuiltRoadRoute:
    engineer_id: str
    legs: tuple[BuiltRoadLeg, ...]
    provider_request_count: int


def build_selected_route_geometry(
    route,
    inputs,
    provider: RoutingProvider | None,
) -> BuiltRoadRoute:
    """Return road shapes for a fixed visit order without changing its metrics."""
    target_keys = {target.target_id: target.cache_key for target in inputs.geodataset.targets}
    entries = {entry.cache_key: entry for entry in inputs.geodataset.entries}
    ids = (route.office_id,) + tuple(stop.request_id for stop in route.stops)
    try:
        cache_keys = tuple(target_keys[item_id] for item_id in ids)
        points = tuple(entries[key].coordinates for key in cache_keys)
    except KeyError as error:
        raise RoutingUnavailableError("routing_unavailable") from error
    if any(point is None for point in points):
        raise RoutingUnavailableError("routing_unavailable")
    coordinates = tuple(point for point in points if isinstance(point, Coordinates))

    cached = tuple(
        inputs.road_cache.geometry_for(origin, destination)
        for origin, destination in pairwise(cache_keys)
    )
    if all(
        geometry is not None or origin == destination
        for geometry, origin, destination in zip(
            cached, cache_keys[:-1], cache_keys[1:], strict=True
        )
    ):
        legs = tuple(
            BuiltRoadLeg(
                request_id=stop.request_id,
                sequence=index,
                geometry=geometry.coordinates if geometry else None,
                source="cache" if geometry else "same_location",
            )
            for index, (stop, geometry) in enumerate(zip(route.stops, cached, strict=True), 1)
        )
        return BuiltRoadRoute(route.engineer_id, legs, 0)

    if provider is None:
        raise RoutingUnavailableError("routing_unavailable")
    results = provider.get_route_sequence(coordinates)
    if len(results) != len(route.stops):
        raise RoutingUnavailableError("routing_unavailable")
    legs = tuple(
        BuiltRoadLeg(
            request_id=stop.request_id,
            sequence=index,
            geometry=result.geometry.coordinates,
            source="on_demand",
        )
        for index, (stop, result) in enumerate(zip(route.stops, results, strict=True), 1)
    )
    return BuiltRoadRoute(route.engineer_id, legs, 1)
