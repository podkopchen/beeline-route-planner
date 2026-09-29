"""Lazy, offline, immutable input and plan snapshots for the read-only API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.models.diagnostics import DiagnosticReport
from app.models.enriched_dataset import EnrichedDataset
from app.models.geo import GeoCacheEntry, GeoDataset
from app.models.workforce import WorkforceDataset
from app.services.baseline import build_baseline_plan
from app.services.csv_loader import load_all_synthetic_sources
from app.services.diagnostics import diagnose_optimized_plan
from app.services.enrichment import enrich_normalized_dataset
from app.services.geocache import build_offline_geodataset
from app.services.normalization import normalize_loaded_source_data
from app.services.optimizer import build_optimized_plan
from app.services.replan import build_replanned_plan
from app.services.road_cache import RoadCacheRepository, road_cache_repository
from app.services.route_geometry import BuiltRoadRoute, build_selected_route_geometry
from app.services.workforce import build_workforce_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = PROJECT_ROOT.parent


@dataclass(frozen=True)
class Inputs:
    enriched: EnrichedDataset
    workforce: WorkforceDataset
    geodataset: GeoDataset
    road_cache: RoadCacheRepository


@dataclass(frozen=True)
class PlanSnapshot:
    plan_kind: str
    plan: object
    diagnostics: DiagnosticReport | None


class RouteFlowSnapshotRepository:
    """Build snapshots only on demand; all underlying planning remains offline."""

    def __init__(self) -> None:
        self._inputs: Inputs | None = None
        self._plans: dict[tuple[str, str, str], PlanSnapshot] = {}
        self._route_geometries: dict[tuple[str, str, str, str, str | None], BuiltRoadRoute] = {}
        self._route_geometry_lock = Lock()

    def inputs(self) -> Inputs:
        if self._inputs is None:
            source_root = WORKSPACE_ROOT / "Датасет" / "Обезличивание"
            enriched = enrich_normalized_dataset(
                normalize_loaded_source_data(load_all_synthetic_sources(source_root))
            )
            workforce = build_workforce_dataset(enriched)
            cache_path = PROJECT_ROOT / "data" / "generated" / "geocache.json"
            entries = tuple(
                GeoCacheEntry.model_validate(item)
                for item in json.loads(cache_path.read_text(encoding="utf-8"))[
                    "entries"
                ]
            )
            road_cache = road_cache_repository(
                PROJECT_ROOT / "data" / "generated" / "road_matrix_cache.json",
                PROJECT_ROOT / "data" / "generated" / "road_geometry_cache.json",
            )
            self._inputs = Inputs(
                enriched=enriched,
                workforce=workforce,
                geodataset=build_offline_geodataset(enriched, workforce, entries),
                road_cache=road_cache,
            )
        return self._inputs

    def plan(
        self, plan_kind: str, territory: str, traffic_profile: str
    ) -> PlanSnapshot:
        key = (plan_kind, territory, traffic_profile)
        if key not in self._plans:
            inputs = self.inputs()
            if plan_kind == "baseline":
                plan = build_baseline_plan(
                    inputs.enriched,
                    inputs.workforce,
                    inputs.geodataset,
                    territory,
                    traffic_profile,
                    inputs.road_cache,
                )
                diagnostics = None
            elif plan_kind == "optimized":
                plan = build_optimized_plan(
                    inputs.enriched,
                    inputs.workforce,
                    inputs.geodataset,
                    territory,
                    traffic_profile,
                    inputs.road_cache,
                )
                diagnostics = diagnose_optimized_plan(
                    plan,
                    inputs.enriched,
                    inputs.workforce,
                    inputs.geodataset,
                    inputs.road_cache,
                )
            else:
                raise ValueError(f"Unknown plan kind: {plan_kind}")
            self._plans[key] = PlanSnapshot(plan_kind, plan, diagnostics)
        return self._plans[key]

    def replan(self, event_id: str, traffic_profile: str):
        """Build a fresh stateless event result; cached base snapshots stay immutable."""
        inputs = self.inputs()
        event = next(
            (item for item in inputs.workforce.events if item.event_id == event_id),
            None,
        )
        if event is None:
            raise KeyError(event_id)
        return build_replanned_plan(
            inputs.enriched,
            inputs.workforce,
            inputs.geodataset,
            event,
            traffic_profile,
            inputs.road_cache,
        )

    def route_geometry(
        self,
        plan_kind: str,
        territory: str,
        traffic_profile: str,
        engineer_id: str,
        provider,
        event_id: str | None = None,
    ) -> BuiltRoadRoute:
        """Hydrate one fixed route, once per process, without mutating its plan."""
        key = (plan_kind, territory, traffic_profile, engineer_id, event_id)
        with self._route_geometry_lock:
            cached = self._route_geometries.get(key)
            if cached is not None:
                return cached
            plan = (
                self.replan(event_id, traffic_profile).replanned_plan
                if event_id
                else self.plan(plan_kind, territory, traffic_profile).plan
            )
            route = next(
                (item for item in plan.routes if item.engineer_id == engineer_id),
                None,
            )
            if route is None:
                raise KeyError(engineer_id)
            built = build_selected_route_geometry(route, self.inputs(), provider)
            self._route_geometries[key] = built
            return built
