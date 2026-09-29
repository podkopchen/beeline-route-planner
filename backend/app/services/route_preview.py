"""Coordinate-first foundation for a future editor; no geocoding or visit reordering.

The caller supplies an explicit provider. No configured/global provider is created,
and no cache miss is converted into fabricated road geometry. Results are ephemeral.
"""

from __future__ import annotations

import math

from pydantic import Field

from app.core.traffic_config import traffic_profile
from app.models.geo import Coordinates
from app.models.normalized_dataset import StrictModel
from app.models.road import GeoJsonLineString
from app.services.routing import RoutingProvider, RoutingUnavailableError


class CoordinateRouteRequest(StrictModel):
    points: tuple[Coordinates, ...] = Field(min_length=2, max_length=50)
    traffic_profile_id: str = "standard"


class CoordinateLeg(StrictModel):
    sequence: int
    origin: Coordinates
    destination: Coordinates
    distance_km: float
    base_duration_seconds: float
    travel_minutes: int
    geometry: GeoJsonLineString | None


class CoordinateRoute(StrictModel):
    traffic_profile_id: str
    legs: tuple[CoordinateLeg, ...]
    distance_km: float
    travel_minutes: int


def build_coordinate_route(
    request: CoordinateRouteRequest, provider: RoutingProvider | None
) -> CoordinateRoute:
    """Evaluate one supplied driving sequence. This does not optimize stop order."""
    profile = traffic_profile(request.traffic_profile_id)
    legs = []
    local_results = {}
    for sequence, (origin, destination) in enumerate(
        zip(request.points, request.points[1:], strict=False), 1
    ):
        if origin == destination:
            distance, seconds, geometry = 0.0, 0.0, None
        else:
            if provider is None:
                raise RoutingUnavailableError("routing_unavailable")
            key = (origin.latitude, origin.longitude, destination.latitude, destination.longitude)
            if key not in local_results:
                local_results[key] = provider.get_route(origin, destination)
            result = local_results[key]
            distance, seconds, geometry = result.distance_km, result.base_duration_seconds, result.geometry
        legs.append(CoordinateLeg(
            sequence=sequence, origin=origin, destination=destination,
            distance_km=distance, base_duration_seconds=seconds,
            travel_minutes=math.ceil(seconds / 60 * profile.traffic_factor),
            geometry=geometry,
        ))
    return CoordinateRoute(
        traffic_profile_id=profile.profile_id, legs=tuple(legs),
        distance_km=round(sum(leg.distance_km for leg in legs), 6),
        travel_minutes=sum(leg.travel_minutes for leg in legs),
    )
