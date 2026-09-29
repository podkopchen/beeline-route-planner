import type { DashboardData, ReplanResponse, RequestItem } from "../types/api";

export function replanView(base: DashboardData, result: ReplanResponse): DashboardData {
  const assignments = new Map(result.replanned_plan.routes.flatMap(route => route.stops.map(stop => [stop.request_id, { engineer_id: route.engineer_id, sequence: stop.sequence }] as const)));
  const committed = new Set(result.committed_stops?.map(stop => stop.request_id));
  const added = new Set(result.diff.added_urgent_request_ids);
  const reassigned = new Set(result.diff.reassigned?.map(item => item.request_id));
  const cancelled = new Set(result.diff.cancelled_request_ids);
  const requests: RequestItem[] = base.requests.map(item => ({ ...item, assignment: assignments.get(item.request_id) ?? null, assignment_status: assignments.has(item.request_id) ? "assigned" : "unassigned", mapStatus: committed.has(item.request_id) ? "зафиксировано" : cancelled.has(item.request_id) ? "снято" : reassigned.has(item.request_id) ? "переназначено" : undefined }));
  const payload = result.event?.payload;
  if (payload?.synthetic_request_id && !requests.some(item => item.request_id === payload.synthetic_request_id)) {
    // Current API exposes urgent schedule but not geometry. Do not guess/inherit
    // a source request on the frontend: keep unknown coordinates explicit.
    requests.push({ request_id: payload.synthetic_request_id, territory: result.event!.territory, address: payload.synthetic_address ?? "Synthetic event", window_start: payload.window_start!, window_end: payload.window_end!, service_duration_min: payload.service_duration_min!, required_skills: payload.required_skill ? [payload.required_skill] : [], priority: "urgent", assignment_status: assignments.has(payload.synthetic_request_id) ? "assigned" : "unassigned", assignment: assignments.get(payload.synthetic_request_id) ?? null, diagnostic: null, coordinates: { latitude: null, longitude: null, source: "unavailable_in_api", precision: null, approximate: null, warning: "Координаты urgent-заявки не переданы API" }, mapStatus: added.has(payload.synthetic_request_id) ? "добавлено" : "событие" });
  }
  return { ...base, requests, plan: result.replanned_plan };
}
