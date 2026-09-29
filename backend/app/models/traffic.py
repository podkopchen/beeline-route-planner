"""Typed offline traffic-scenario contracts for future plan/API consumers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.normalized_dataset import StrictModel

TrafficProfileId = Literal["standard", "moderate", "peak"]


class TrafficProfile(StrictModel):
    profile_id: TrafficProfileId
    display_name: str
    traffic_factor: float = Field(gt=0)
    description: str
