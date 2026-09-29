"""Deterministic offline proxy coordinates for synthetic hackathon data only."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from app.models.enriched_dataset import EnrichedDataset
from app.models.geo import Coordinates, GeoCacheEntry, GeoDataset
from app.models.workforce import WorkforceDataset

GEO_PROXY_SEED = 2026
PROXY_JITTER_DEGREES = 0.0025
PROXY_WARNING = "Synthetic proxy for hackathon data; not a geocoded address."
LEGACY_WARNING = "Legacy coordinate has unknown precision; treat as approximate."


def enrich_geodataset_with_proxies(
    geodataset: GeoDataset, enriched: EnrichedDataset, workforce: WorkforceDataset
) -> GeoDataset:
    """Resolve every remaining cache key without network calls or manual coordinates."""

    territory_by_key, locality_by_key, urgent_by_key = _target_context(
        geodataset, enriched, workforce
    )
    entries = {
        entry.cache_key: _label_existing_entry(entry) for entry in geodataset.entries
    }
    anchors = _anchors(entries, territory_by_key, locality_by_key)

    for key in sorted(entries):
        entry = entries[key]
        if entry.coordinates is not None or key in urgent_by_key:
            continue
        territory = territory_by_key[key]
        anchor = _select_anchor(anchors, territory, locality_by_key[key])
        latitude_delta, longitude_delta = _jitter(key)
        entries[key] = entry.model_copy(
            update={
                "coordinates": Coordinates(
                    latitude=anchor.latitude + latitude_delta,
                    longitude=anchor.longitude + longitude_delta,
                ),
                "source": "synthetic_proxy",
                "geo_source": "synthetic_proxy",
                "status": "resolved",
                "precision": "synthetic_proxy",
                "approximate": True,
                "warning": PROXY_WARNING,
                "geocode_attempted": True,
            }
        )

    for key, territory in urgent_by_key.items():
        request = next(
            item
            for item in enriched.requests
            if item.territory == territory
            and entries[_request_key(geodataset, item.request_id)].coordinates
        )
        source_key = _request_key(geodataset, request.request_id)
        entries[key] = entries[key].model_copy(
            update={
                "coordinates": entries[source_key].coordinates,
                "source": "synthetic_proxy",
                "geo_source": "synthetic_proxy",
                "status": "resolved",
                "precision": "synthetic_proxy",
                "approximate": True,
                "warning": "Synthetic urgent event inherits request location; not a geocoded address.",
                "geocode_attempted": True,
                "location_source_request_id": request.request_id,
            }
        )
    return GeoDataset(
        entries=tuple(entries[key] for key in sorted(entries)),
        targets=geodataset.targets,
    )


def _label_existing_entry(entry: GeoCacheEntry) -> GeoCacheEntry:
    if entry.coordinates is None:
        return entry
    if entry.precision is None:
        return entry.model_copy(
            update={
                "geo_source": "legacy_unknown",
                "precision": "legacy_unknown",
                "approximate": True,
                "warning": LEGACY_WARNING,
            }
        )
    return entry.model_copy(update={"geo_source": entry.geo_source or "nominatim"})


def _target_context(
    geodataset: GeoDataset, enriched: EnrichedDataset, workforce: WorkforceDataset
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    request_by_id = {request.request_id: request for request in enriched.requests}
    office_by_id = {office.office_id: office for office in workforce.offices}
    urgent_by_id = {
        event.payload.synthetic_request_id: event.territory
        for event in workforce.events
        if event.event_type == "urgent_request"
    }
    territories: dict[str, str] = {}
    localities: dict[str, str] = {}
    urgents: dict[str, str] = {}
    for target in geodataset.targets:
        if target.target_id in request_by_id:
            territory = request_by_id[target.target_id].territory
        elif target.target_id in office_by_id:
            territory = office_by_id[target.target_id].territory
        else:
            territory = urgent_by_id[target.target_id]
            urgents[target.cache_key] = territory
        territories[target.cache_key] = territory
        localities[target.cache_key] = _locality(target.address)
    return territories, localities, urgents


def _anchors(
    entries: dict[str, GeoCacheEntry],
    territories: dict[str, str],
    localities: dict[str, str],
) -> dict[tuple[str, str], list[Coordinates]]:
    values: dict[tuple[str, str], list[Coordinates]] = defaultdict(list)
    for key, entry in entries.items():
        if entry.coordinates is not None:
            values[(territories[key], localities[key])].append(entry.coordinates)
            values[(territories[key], "territory")].append(entry.coordinates)
    return values


def _select_anchor(
    anchors: dict[tuple[str, str], list[Coordinates]], territory: str, locality: str
) -> Coordinates:
    candidates = anchors.get((territory, locality)) or anchors[(territory, "territory")]
    return Coordinates(
        latitude=sum(item.latitude for item in candidates) / len(candidates),
        longitude=sum(item.longitude for item in candidates) / len(candidates),
    )


def _jitter(cache_key: str) -> tuple[float, float]:
    digest = hashlib.sha256(f"{GEO_PROXY_SEED}:{cache_key}".encode()).digest()
    latitude = (
        int.from_bytes(digest[:8], "big") / 2**64 * 2 - 1
    ) * PROXY_JITTER_DEGREES
    longitude = (
        int.from_bytes(digest[8:16], "big") / 2**64 * 2 - 1
    ) * PROXY_JITTER_DEGREES
    return latitude, longitude


def _locality(address: str) -> str:
    text = address.casefold()
    if "\u043a\u0430\u0448\u0438\u0440" in text:
        return "kashira"
    if "\u0441\u0442\u0443\u043f\u0438\u043d" in text:
        return "stupino"
    if "\u0434\u043e\u043c\u043e\u0434\u0435\u0434" in text:
        return "domodedovo"
    return "moscow"


def _request_key(geodataset: GeoDataset, request_id: str) -> str:
    return next(
        target.cache_key
        for target in geodataset.targets
        if target.target_id == request_id
    )
