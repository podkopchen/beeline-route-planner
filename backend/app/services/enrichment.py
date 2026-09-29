"""Deterministic DATA-003 enrichment for normalized request data."""

from __future__ import annotations

import hashlib
import json
from typing import Final

from app.core.enrichment_config import ENRICHMENT_CONFIG, EnrichmentConfig
from app.models.enriched_dataset import EnrichedDataset, EnrichedRequest
from app.models.normalized_dataset import NormalizedDataset, NormalizedRequest

NORMAL_PRIORITY: Final = "normal"
NO_TRANSPORT: Final = "none"
CAR_TRANSPORT: Final = "car"


class EnrichmentError(ValueError):
    """Raised when a normalized request cannot satisfy the explicit rule config."""


def enrich_normalized_dataset(
    normalized_dataset: NormalizedDataset,
    config: EnrichmentConfig = ENRICHMENT_CONFIG,
) -> EnrichedDataset:
    """Create stable planner inputs without mutating normalized records or sources."""

    return EnrichedDataset(
        enrichment_seed=config.seed,
        requests=tuple(
            _enrich_request(request, config) for request in normalized_dataset.requests
        ),
        offices=normalized_dataset.offices,
    )


def canonical_json_bytes(enriched_dataset: EnrichedDataset) -> bytes:
    """Return one repeatable UTF-8 representation for regression checks and artifacts."""

    payload = enriched_dataset.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def enriched_dataset_sha256(enriched_dataset: EnrichedDataset) -> str:
    """Return the SHA-256 of the canonical DATA-003 representation."""

    return hashlib.sha256(canonical_json_bytes(enriched_dataset)).hexdigest()


def _enrich_request(
    request: NormalizedRequest,
    config: EnrichmentConfig,
) -> EnrichedRequest:
    complexity = _derive_complexity(request, config)
    normative = _normative_for(request, config)
    return EnrichedRequest(
        **request.model_dump(),
        required_skills=(_derive_required_skill(request, config),),
        complexity=complexity,
        normative_work_name=normative.work_name,
        technical_work_min=normative.technical_work_min,
        documents_min=normative.documents_min,
        service_duration_min=normative.service_duration_min,
        normative_travel_min=normative.normative_travel_min,
        base_normative_min=normative.base_normative_min,
        priority=NORMAL_PRIORITY,
        transport_requirement=(
            CAR_TRANSPORT
            if _requires_car(request, complexity, config)
            else NO_TRANSPORT
        ),
    )


def _derive_required_skill(
    request: NormalizedRequest,
    config: EnrichmentConfig,
) -> str:
    try:
        return config.bk_skill_rules[request.bk_request_type]
    except KeyError as error:
        raise EnrichmentError(
            f"No required-skill rule for BK type {request.bk_request_type!r}"
        ) from error


def _normative_for(request: NormalizedRequest, config: EnrichmentConfig):
    try:
        return config.bk_normatives[request.bk_request_type]
    except KeyError as error:
        raise EnrichmentError(
            f"No work normative for BK type {request.bk_request_type!r}"
        ) from error


def _derive_complexity(
    request: NormalizedRequest,
    config: EnrichmentConfig,
) -> str:
    if (
        request.bk_request_type in config.high_complexity_bk_types
        or request.hd_request_type in config.high_complexity_hd_types
    ):
        return "high"
    if request.hd_request_type in config.low_complexity_hd_types:
        return "low"
    return "medium"


def _physical_work_increment_count(
    request: NormalizedRequest,
    config: EnrichmentConfig,
) -> int:
    return sum(
        (
            request.connection in config.vehicle_connection_values,
            request.gigabit_connection in config.gigabit_yes_values,
        )
    )


def _requires_car(
    request: NormalizedRequest,
    complexity: str,
    config: EnrichmentConfig,
) -> bool:
    return complexity == "high" or _physical_work_increment_count(request, config) > 0
