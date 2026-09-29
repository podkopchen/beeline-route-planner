import type { FeatureCollection, LineString } from "geojson";
import type { MapLeg } from "./scene";

// Display-only chevrons follow the ordered API polyline, never a snapped/new route.
// Phase is animation time, NOT vehicle position or estimated travel progress.
export function directionArrows(legs: MapLeg[], phase: number, size = 14): FeatureCollection<LineString> {
  const features: FeatureCollection<LineString>["features"] = [];
  for (const leg of legs) {
    if (!leg.selected || leg.routingSource !== "road" || leg.positions.length < 2) continue;
    const lonScale = 111320 * Math.cos(leg.positions[0][1] * Math.PI / 180);
    const segments = leg.positions.slice(1).map((b, i) => {
      const a = leg.positions[i], dx = (b[0] - a[0]) * lonScale, dy = (b[1] - a[1]) * 111320;
      return { a, dx, dy, length: Math.hypot(dx, dy) };
    });
    const total = segments.reduce((sum, s) => sum + s.length, 0);
    const spacing = Math.max(size * 10, total / 24);
    let start = 0, target = ((phase % 1 + 1) % 1 + .05) * spacing;
    for (const s of segments) {
      while (s.length > 0 && target < start + s.length) {
        const t = (target - start) / s.length, ux = s.dx / s.length, uy = s.dy / s.length;
        const x = s.a[0] + s.dx * t / lonScale, y = s.a[1] + s.dy * t / 111320;
        const wing = (side: number) => [x + (-ux * size + side * uy * size * .6) / lonScale, y + (-uy * size - side * ux * size * .6) / 111320];
        features.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [wing(1), [x, y], wing(-1)] } });
        target += spacing;
      }
      start += s.length;
    }
  }
  return { type: "FeatureCollection", features };
}
