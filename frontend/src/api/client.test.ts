import { afterEach, describe, expect, it, vi } from "vitest";

import { applyReplan, buildRoadGeometry, buildQuery, buildRequestsQuery, fetchExplanation } from "./client";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("sends explanation plan, traffic and event context", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ facts: [] })));
  vi.stubGlobal("fetch", fetch);
  await fetchExplanation("east:1", "event-east-urgent-1430", "baseline", "peak");
  const url = new URL(fetch.mock.calls[0][0]);
  expect(url.searchParams.get("plan_kind")).toBe("baseline");
  expect(url.searchParams.get("traffic_profile")).toBe("peak");
  expect(url.searchParams.get("event_id")).toBe("event-east-urgent-1430");
});

it.each(["replan", "geometry"])("expires session on %s POST 401", async kind => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
  const dispatch = vi.spyOn(window, "dispatchEvent");
  const action = kind === "replan" ? applyReplan("event", "standard") : buildRoadGeometry("optimized", "eng", "east", "standard");
  await expect(action).rejects.toThrow("Сессия завершена");
  expect(dispatch).toHaveBeenCalledOnce();
  expect(dispatch.mock.calls[0][0].type).toBe("routeflow:session-expired");
});

describe("buildQuery", () => {
  // UI-001 initially had only this pure scenario: React DOM and Leaflet mocks
  // had not yet been installed. UI-002.1 adds independent component coverage.
  it("serializes the selected API scenario without frontend calculations", () => {
    expect(buildQuery("southeast", "peak")).toBe("territory=southeast&traffic_profile=peak");
  });

  it("serializes territory, profile, plan, assignment filter and pagination", () => {
    expect(buildRequestsQuery("all", "standard", "baseline", "unassigned", 50, 10)).toBe("territory=all&traffic_profile=standard&plan_kind=baseline&assignment_status=unassigned&limit=50&offset=10");
  });
});
