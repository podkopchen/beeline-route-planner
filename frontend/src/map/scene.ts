import type { DashboardData, Filter, Territory, TrafficProfile } from "../types/api";

export type Position = [number, number]; // longitude, latitude
export const trafficColors = { free: "#19865d", moderate: "#d89b16", peak: "#d9534f" };
export const trafficLabels = { free: "свободно", moderate: "умеренно", peak: "пик" };
export type TrafficLevel = keyof typeof trafficColors;
export function segmentLevel(profile: TrafficProfile, engineer: string, sequence: number): TrafficLevel {
  let hash = 2166136261;
  for (const char of `${profile}:${engineer}:${sequence}`) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  const bucket = (hash >>> 0) % 100;
  if (profile === "standard") return bucket < 82 ? "free" : "moderate";
  if (profile === "moderate") return bucket < 38 ? "free" : bucket < 88 ? "moderate" : "peak";
  return bucket < 10 ? "free" : bucket < 48 ? "moderate" : "peak";
}
export interface MapPoint { id: string; position: Position; displayPosition: Position; territory?: string; kind: "office" | "assigned" | "unassigned"; label: string; sequence?: number; engineer?: string; approximate: boolean; detail: string; }
export interface MapLeg { id: string; engineer: string; sequence: number; positions: Position[]; selected: boolean; level: TrafficLevel; routingSource: "road" | "fallback" | "unresolved"; detail: string; }
export interface Scene { points: MapPoint[]; legs: MapLeg[]; focusPositions: Position[]; missing: string[]; overview: boolean; }
export function position(coordinates?: { longitude: number | null; latitude: number | null }): Position | undefined {
  if (!coordinates || coordinates.longitude === null || coordinates.latitude === null) return;
  const { longitude, latitude } = coordinates;
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 85) return;
  return [longitude, latitude];
}
function displayPositions(points: MapPoint[]): MapPoint[] {
  const groups = new Map<string, MapPoint[]>();
  for (const point of points) {
    const key = `${point.position[0].toFixed(4)}:${point.position[1].toFixed(4)}`;
    groups.set(key, [...(groups.get(key) ?? []), point]);
  }
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    group.sort((a, b) => a.id.localeCompare(b.id)).forEach((point, index) => {
      const angle = (index * 137.508) * Math.PI / 180;
      const ring = 1 + Math.floor(index / 8);
      const radius = .00018 * ring;
      point.displayPosition = [point.position[0] + Math.cos(angle) * radius, point.position[1] + Math.sin(angle) * radius];
    });
  }
  return points;
}
export function sceneFor(data: DashboardData | undefined, filter: Filter, selected: string | undefined, profile: TrafficProfile, territory: Territory = "east"): Scene {
  const scene: Scene = { points: [], legs: [], focusPositions: [], missing: [], overview: territory === "all" && !selected };
  if (!data) return scene;
  const requests = new Map(data.requests.map(item => [item.request_id, item]));
  const offices = new Map(data.territories.map(item => [item.office_id, item]));
  const selectedRoute = data.plan.routes.find(route => route.engineer_id === selected);
  const selectedStops = new Map(selectedRoute?.stops.map(stop => [stop.request_id, stop]));
  for (const office of data.territories) {
    const point = position(office.office_coordinates);
    if (point) scene.points.push({ id: office.office_id, position: point, displayPosition: point, territory: office.territory, kind: "office", label: "⌂", engineer: selectedRoute?.office_id === office.office_id ? selected : undefined, approximate: Boolean(office.office_coordinates.approximate), detail: `Офис · ${office.office_id}. ${selectedRoute?.office_id === office.office_id ? `Выбранный маршрут: ${selected}. ` : ""}${office.office_coordinates.approximate ? "≈ Приближённая координата. " : ""}${office.office_coordinates.warning ?? ""}` });
    else scene.missing.push(office.office_id);
  }
  for (const request of data.requests) {
    if (filter !== "all" && filter !== request.assignment_status && !selectedStops.has(request.request_id)) continue;
    const point = position(request.coordinates);
    if (!point) { scene.missing.push(request.request_id); continue; }
    const stop = selectedStops.get(request.request_id);
    scene.points.push({ id: request.request_id, position: point, displayPosition: point, territory: request.territory, kind: request.assignment_status, label: stop ? String(stop.sequence) : request.assignment_status === "unassigned" ? "!" : "", sequence: stop?.sequence, engineer: request.assignment?.engineer_id, approximate: Boolean(request.coordinates.approximate), detail: `${request.request_id} · ${request.address}\n${request.assignment?.engineer_id ?? "Не назначена"}${request.mapStatus ? ` · ${request.mapStatus}` : ""}\n${request.coordinates.approximate ? "≈ Приближённая координата. " : ""}${request.coordinates.warning ?? ""}` });
  }
  for (const route of data.plan.routes) {
    let previous = position(offices.get(route.office_id)?.office_coordinates);
    for (const stop of route.stops) {
      const next = position(requests.get(stop.request_id)?.coordinates);
      if (!next) scene.missing.push(stop.request_id);
      const level = segmentLevel(profile, route.engineer_id, stop.sequence);
      if (previous && next && (!scene.overview || route.engineer_id === selected)) {
        const hasRoadGeometry = (stop.geometry_status === "road" || stop.routing_source === "road") && Boolean(stop.geometry?.length);
        const routingSource = hasRoadGeometry ? "road" : "fallback";
        const positions = hasRoadGeometry ? stop.geometry! : [previous, next];
        const description = routingSource === "road"
          ? `${trafficLabels[level]} · Дорожная модель + сценарный коэффициент. Не текущие пробки.`
          : `${trafficLabels[level]} · Модельный сценарий, не данные о текущих пробках. ${stop.routing_warning ?? "Расчётный путь: дорожная геометрия недоступна."}`;
        scene.legs.push({ id: `${route.engineer_id}:${stop.sequence}`, engineer: route.engineer_id, sequence: stop.sequence, positions, selected: route.engineer_id === selected, level, routingSource, detail: `Участок ${stop.sequence} · ${stop.adjusted_travel_minutes ?? stop.travel_minutes} мин · ${stop.distance_km.toFixed(3)} км\n${description}` });
      }
      previous = next; // Never bridge an unknown stop or add a return leg.
    }
  }
  const selectedOffice = position(offices.get(selectedRoute?.office_id ?? "")?.office_coordinates);
  scene.focusPositions = selectedRoute ? [selectedOffice, ...selectedRoute.stops.map(stop => position(requests.get(stop.request_id)?.coordinates))].filter((item): item is Position => Boolean(item)) : scene.points.map(point => point.position);
  scene.points = displayPositions(scene.points);
  scene.missing = [...new Set(scene.missing)];
  scene.legs.sort((a, b) => Number(a.selected) - Number(b.selected));
  scene.points.sort((a, b) => Number(Boolean(a.sequence) || a.kind === "office") - Number(Boolean(b.sequence) || b.kind === "office"));
  return scene;
}
