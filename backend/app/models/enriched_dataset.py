"""Strict DATA-003 models with synthetic planner inputs and provenance."""

from __future__ import annotations

from typing import Literal

from app.models.normalized_dataset import (
    NormalizedOffice,
    NormalizedRequest,
    StrictModel,
)

RequiredSkill = Literal["installation", "subscriber_support", "network_repair"]
Complexity = Literal["low", "medium", "high"]
Priority = Literal["normal", "urgent"]
TransportRequirement = Literal["none", "car"]


class EnrichedRequest(NormalizedRequest):
    """A normalized request plus deterministic synthetic planner attributes."""

    required_skills: tuple[RequiredSkill, ...]
    complexity: Complexity
    normative_work_name: str
    technical_work_min: int
    documents_min: int
    service_duration_min: int
    normative_travel_min: int
    base_normative_min: int
    priority: Priority
    transport_requirement: TransportRequirement


class EnrichedDataset(StrictModel):
    """The canonical input for future planner stages."""

    enrichment_seed: int
    requests: tuple[EnrichedRequest, ...]
    offices: tuple[NormalizedOffice, ...]
