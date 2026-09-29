"""Public deterministic explanation contract; facts are derived, never generated."""

from __future__ import annotations

from typing import Literal

from app.models.normalized_dataset import StrictModel


class ExplanationFact(StrictModel):
    key: str
    label_ru: str
    value: str


class RequestExplanation(StrictModel):
    request_id: str
    status: Literal["assigned", "unassigned"]
    title: str
    summary: str
    facts: tuple[ExplanationFact, ...]
    plan_kind: Literal["baseline", "optimized"]
    territory: str
    traffic_profile: str
    event_id: str | None = None
    evidence_scope: str | None = None
