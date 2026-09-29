"""Offline-only geo-cache assembly; online resolution belongs to an explicit script."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from app.models.enriched_dataset import EnrichedDataset
from app.models.geo import GeoCacheEntry, GeoDataset, GeoTarget
from app.models.workforce import WorkforceDataset

_ADDRESS_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_ADDRESS_SPACES = re.compile(r"\s+", flags=re.UNICODE)
UNRESOLVED_WARNING = "Coordinates are unavailable; no distance is calculated."


def normalize_address(address: str) -> str:
    """Normalize formatting only; the original address remains on its source entity."""

    normalized = _ADDRESS_PUNCTUATION.sub(" ", address.casefold())
    return _ADDRESS_SPACES.sub(" ", normalized).strip()


def geocache_key(address: str) -> str:
    """Create a stable SHA-256 key from the normalized address."""

    normalized = normalize_address(address)
    if not normalized:
        raise ValueError("Address must not normalize to an empty cache key")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_offline_geodataset(
    enriched_dataset: EnrichedDataset,
    workforce: WorkforceDataset,
    existing_entries: Iterable[GeoCacheEntry] = (),
) -> GeoDataset:
    """Assemble targets without network access and retain any validated prior cache entry."""

    entries_by_key = {entry.cache_key: entry for entry in existing_entries}
    targets = _geo_targets(enriched_dataset, workforce)
    for target in targets:
        entries_by_key.setdefault(
            target.cache_key,
            GeoCacheEntry(
                cache_key=target.cache_key,
                normalized_address=normalize_address(target.address),
                coordinates=None,
                source="unresolved",
                status="unresolved",
                warning=UNRESOLVED_WARNING,
            ),
        )
    return GeoDataset(
        entries=tuple(entries_by_key[key] for key in sorted(entries_by_key)),
        targets=targets,
    )


def _geo_targets(
    enriched_dataset: EnrichedDataset,
    workforce: WorkforceDataset,
) -> tuple[GeoTarget, ...]:
    targets = [
        GeoTarget(
            target_id=request.request_id,
            target_kind="request",
            address=request.source_address,
            cache_key=geocache_key(request.source_address),
        )
        for request in enriched_dataset.requests
    ]
    targets.extend(
        GeoTarget(
            target_id=office.office_id,
            target_kind="office",
            address=office.source_address,
            cache_key=geocache_key(office.source_address),
        )
        for office in workforce.offices
    )
    targets.extend(
        GeoTarget(
            target_id=event.payload.synthetic_request_id,
            target_kind="synthetic_event",
            address=event.payload.synthetic_address,
            cache_key=geocache_key(event.payload.synthetic_address),
        )
        for event in workforce.events
        if event.event_type == "urgent_request"
    )
    return tuple(targets)
