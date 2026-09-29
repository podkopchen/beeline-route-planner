export type Territory = "all" | "east" | "southeast" | "southcenter";
export type TrafficProfile = "standard" | "moderate" | "peak";
export type Filter = "all" | "assigned" | "unassigned";
export type PlanKind = "baseline" | "optimized";
export interface AuthUser { username: string; display_name: string; role: "dispatcher" | string; }
export interface Coordinates { latitude: number | null; longitude: number | null; source: string; precision: string | null; approximate: boolean | null; warning: string | null; }
export interface RequestItem { request_id: string; territory: Exclude<Territory, "all">; address: string; window_start: string; window_end: string; service_duration_min: number; required_skills: string[]; priority: string; assignment_status: Exclude<Filter, "all">; assignment: { engineer_id: string; sequence: number } | null; diagnostic: { text_ru: string } | null; coordinates: Coordinates; mapStatus?: string; }
export interface Summary { assigned_count: number; unassigned_count: number; active_engineer_count: number; total_distance_km: number; total_travel_minutes: number; total_service_minutes: number; total_waiting_minutes: number; }
export interface Stop { request_id: string; sequence: number; arrival: string; service_start: string; service_end: string; waiting_minutes: number; travel_minutes: number; distance_km: number; base_travel_minutes?: number; adjusted_travel_minutes?: number; routing_source?: "road" | "fallback" | "unresolved"; geometry?: [number, number][] | null; geometry_status?: "road" | "same_location" | "non_car_transport" | "fallback_only" | "matrix_missing" | "geometry_missing" | "unresolved"; geometry_source?: "cache" | "on_demand" | "same_location"; routing_warning?: string | null; }
export interface Plan { summary: Summary; routes: { engineer_id: string; office_id: string; visit_count: number; distance_km: number; travel_minutes: number; service_minutes: number; waiting_minutes: number; route_end: string | null; stops: Stop[] }[]; }
export interface Engineer { engineer_id: string; office_id: string; skills: string[]; transport: string; shift_start: string; shift_end: string; }
export interface TerritoryItem { territory: Exclude<Territory, "all">; office_id: string; office_coordinates: Coordinates; }
export interface DashboardData { requests: RequestItem[]; plan: Plan; baseline: Summary; optimized: Summary; engineers: Engineer[]; territories: TerritoryItem[]; }
export interface RoadGeometryRoute {
  engineer_id: string;
  provider_request_count: number;
  preserves_plan: true;
  legs: { request_id: string; sequence: number; geometry: [number, number][] | null; source: "cache" | "on_demand" | "same_location" }[];
}

// Existing replan response fields, projected for display only. No API additions.
export interface ReplanResponse {
  replanned_plan: Plan;
  event?: { event_id: string; territory: Exclude<Territory, "all">; occurred_at: string; payload: { synthetic_request_id?: string; synthetic_address?: string; required_skill?: string; service_duration_min?: number; window_start?: string; window_end?: string } };
  committed_stops?: { engineer_id: string; request_id: string }[];
  outcome?: { status: string; message_ru: string };
  diff: { emergency_reserve_activated: boolean; activated_reserve_engineer_id: string | null; committed_visit_count: number; added_urgent_request_ids?: string[]; cancelled_request_ids?: string[]; reassigned?: { request_id: string; before_engineer_id: string; after_engineer_id: string }[]; affected_engineer_ids?: string[]; newly_unassigned_request_ids?: string[]; newly_assigned_request_ids?: string[] };
}
