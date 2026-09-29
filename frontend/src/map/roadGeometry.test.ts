import { describe, expect, it } from "vitest";

import { dashboard } from "../test/fixtures";
import { applyRoadGeometry } from "./roadGeometry";

describe("selected road geometry overlay", () => {
  it("replaces only geometry and preserves published route metrics", () => {
    const original = structuredClone(dashboard);
    const result = applyRoadGeometry(dashboard, {
      "eng-east-01": {
        engineer_id: "eng-east-01",
        provider_request_count: 1,
        preserves_plan: true,
        legs: [{ request_id: "east-1", sequence: 1, geometry: [[37.5, 55.7], [37.6, 55.8]], source: "on_demand" }],
      },
    });
    expect(result.plan.routes[0].stops[0]).toMatchObject({
      geometry_status: "road",
      geometry_source: "on_demand",
      travel_minutes: original.plan.routes[0].stops[0].travel_minutes,
      distance_km: original.plan.routes[0].stops[0].distance_km,
    });
    expect(result.plan.summary).toEqual(original.plan.summary);
    expect(dashboard).toEqual(original);
  });
});
