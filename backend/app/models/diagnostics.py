"""Evidence-based diagnostics for unassigned optimized requests."""

from __future__ import annotations

from typing import Literal

from app.models.normalized_dataset import StrictModel

DiagnosticCode = Literal[
    "no_territory_engineer",
    "skill_uncovered",
    "transport_uncovered",
    "window_shift_infeasible",
    "final_plan_insertion_infeasible",
]


class UnassignedDiagnostic(StrictModel):
    request_id: str
    code: DiagnosticCode
    text_ru: str
    scope: str
    territory_engineer_count: int
    skill_engineer_count: int
    transport_engineer_count: int
    standalone_feasible_engineer_count: int
    checked_route_count: int
    checked_route_positions: int
    traffic_profile_id: str


class DiagnosticReport(StrictModel):
    traffic_profile_id: str
    diagnostics: tuple[UnassignedDiagnostic, ...]
