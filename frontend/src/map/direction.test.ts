import { expect, it } from "vitest";
import { directionArrows } from "./direction";
import type { MapLeg } from "./scene";

const leg: MapLeg = { id: "e:1", engineer: "e", sequence: 1, positions: [[37, 55], [37.01, 55], [37.01, 55.01]], selected: true, level: "free", routingSource: "road", detail: "" };
it("arrows follow ordered road geometry and advance without mutating it", () => {
  const before = JSON.stringify(leg);
  const a = directionArrows([leg], 0), b = directionArrows([leg], .5);
  expect(a).toEqual(directionArrows([leg], 0));
  expect(a).not.toEqual(b);
  const [left, tip, right] = a.features[0].geometry.coordinates;
  expect(tip[0]).toBeGreaterThan(left[0]);
  expect(tip[0]).toBeGreaterThan(right[0]);
  expect(tip[1]).toBe(55);
  expect(JSON.stringify(leg)).toBe(before);
});
it("never animates fallback or inactive routes and handles zero-length legs", () => {
  expect(directionArrows([{ ...leg, routingSource: "fallback" }, { ...leg, selected: false }], 0).features).toEqual([]);
  expect(directionArrows([{ ...leg, positions: [[37, 55], [37, 55]] }], 0).features).toEqual([]);
});
