import { describe, expect, it } from "vitest";
import { dashboard } from "../test/fixtures";
import type { DashboardData, ReplanResponse, TrafficProfile } from "../types/api";
import { replanView } from "./replanView";
import { sceneFor, segmentLevel } from "./scene";

function withOffice(): DashboardData {
  return { ...dashboard, territories: [{ territory: "east", office_id: "office-east", office_coordinates: { ...dashboard.requests[0].coordinates, longitude: 37.55 } }] };
}

describe("API geometry and visual scenarios", () => {
  it.each<TrafficProfile>(["standard", "moderate", "peak"])("%s colors are deterministic and leave plan metrics untouched", profile => {
    const source = withOffice(), before = JSON.stringify(source);
    const first = sceneFor(source, "all", "eng-east-01", profile);
    expect(sceneFor(source, "all", "eng-east-01", profile)).toEqual(first);
    expect(first.legs[0].detail).toContain("15 мин · 12.300 км");
    expect(first.legs[0].detail).toContain("Модельный сценарий, не данные о текущих пробках");
    const levels = Array.from({ length: 1000 }, (_, i) => segmentLevel(profile, "eng-east-01", i + 1));
    expect(new Set(levels)).toEqual(new Set(profile === "standard" ? ["free", "moderate"] : ["free", "moderate", "peak"]));
    if (profile === "standard") expect(levels.filter(x => x === "free").length).toBeGreaterThan(700);
    if (profile === "peak") expect(levels.filter(x => x !== "free").length).toBeGreaterThan(800);
    expect(JSON.stringify(source)).toBe(before);
  });
  it("starts at the API office, preserves coordinates and adds no return", () => {
    const scene = sceneFor(withOffice(), "all", "eng-east-01", "standard");
    expect(scene.legs).toHaveLength(1);
    expect(scene.legs[0].positions).toEqual([[37.55, 55.7], [37.6, 55.7]]);
    expect(scene.points.find(x => x.id === "east-1")?.sequence).toBe(1);
    expect(scene.points.find(x => x.id === "east-2")?.kind).toBe("unassigned");
    expect(scene.points.find(x => x.id === "east-1")?.detail).toContain("≈");
  });
  it("uses deterministic display-only offsets for overlapping markers", () => {
    const source = withOffice();
    source.requests[1] = { ...source.requests[1], coordinates: source.requests[0].coordinates };
    const first = sceneFor(source, "all", "eng-east-01", "standard");
    const second = sceneFor(source, "all", "eng-east-01", "standard");
    expect(first.points.map(point => point.displayPosition)).toEqual(second.points.map(point => point.displayPosition));
    expect(first.points.find(point => point.id === "east-1")?.position).toEqual([37.6, 55.7]);
    expect(first.points.find(point => point.id === "east-1")?.displayPosition).not.toEqual(first.points.find(point => point.id === "east-2")?.displayPosition);
  });
  it("renders all-mode as three compact groups without route lines until selection", () => {
    const source = withOffice();
    const overview = sceneFor(source, "all", undefined, "standard", "all");
    expect(overview.overview).toBe(true);
    expect(overview.legs).toEqual([]);
    expect(overview.focusPositions.length).toBe(overview.points.length);
    const focused = sceneFor(source, "all", "eng-east-01", "standard", "all");
    expect(focused.overview).toBe(false);
    expect(focused.legs.some(leg => leg.selected)).toBe(true);
  });
  it("keeps urgent/reserve schedule but never fabricates missing urgent geometry", () => {
    const base = withOffice(), before = JSON.stringify(base);
    const result: ReplanResponse = {
      event: { event_id: "event-east-urgent-1430", territory: "east", occurred_at: "2026-08-17T14:30:00+03:00", payload: { synthetic_request_id: "urgent-east", required_skill: "network_repair", service_duration_min: 80, window_start: "2026-08-17T15:00:00+03:00", window_end: "2026-08-17T17:00:00+03:00" } },
      replanned_plan: { ...base.plan, routes: [...base.plan.routes, { ...base.plan.routes[0], engineer_id: "reserve-east-emergency-01", stops: [{ ...base.plan.routes[0].stops[0], request_id: "urgent-east" }] }] },
      diff: { emergency_reserve_activated: true, activated_reserve_engineer_id: "reserve-east-emergency-01", committed_visit_count: 29, added_urgent_request_ids: ["urgent-east"] },
    };
    const view = replanView(base, result), scene = sceneFor(view, "all", "reserve-east-emergency-01", "standard");
    expect(view.requests.find(x => x.request_id === "urgent-east")?.mapStatus).toBe("добавлено");
    expect(scene.missing).toEqual(["urgent-east"]);
    expect(scene.legs.filter(x => x.engineer === "reserve-east-emergency-01")).toEqual([]);
    expect(JSON.stringify(base)).toBe(before);
  });
});
