import type {
  DashboardData,
  PlanKind,
  Territory,
  TrafficProfile,
  ReplanResponse,
  RoadGeometryRoute,
  AuthUser,
} from "../types/api";
const localHost = typeof window !== "undefined" && window.location.hostname === "127.0.0.1" ? "127.0.0.1" : "localhost";
const baseUrl = import.meta.env.VITE_API_BASE_URL || `http://${localHost}:8000`;

async function authRequest(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, credentials: "include" });
  if (response.status === 401 && !path.startsWith("/api/v1/auth/")) {
    window.dispatchEvent(new CustomEvent("routeflow:session-expired"));
    throw new Error("Сессия завершена. Войдите снова.");
  }
  return response;
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const response = await authRequest("/api/v1/auth/me");
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Сервис авторизации недоступен.");
  return response.json();
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const response = await authRequest("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const body = await response.json().catch((): { detail?: string } => ({}));
    throw new Error(response.status === 401 ? "Неверный логин или пароль." : body.detail ?? "Не удалось выполнить вход.");
  }
  return response.json();
}

export async function logout(): Promise<void> {
  const response = await authRequest("/api/v1/auth/logout", { method: "POST" });
  if (!response.ok && response.status !== 204) throw new Error("Не удалось завершить сеанс.");
}
export async function fetchExplanation(
  requestId: string,
  eventId?: string,
  planKind: PlanKind = "optimized",
  trafficProfile: TrafficProfile = "standard",
): Promise<{
  title: string;
  summary: string;
  facts: { label_ru: string; value: string }[];
  evidence_scope?: string;
}> {
  const query = new URLSearchParams({ plan_kind: planKind, traffic_profile: trafficProfile });
  if (eventId) query.set("event_id", eventId);
  return get(`/api/v1/requests/${encodeURIComponent(requestId)}/explanation?${query}`);
}
export async function applyReplan(
  eventId: string,
  trafficProfile: TrafficProfile,
): Promise<ReplanResponse> {
  const response = await authRequest("/api/v1/replan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event_id: eventId,
      traffic_profile: trafficProfile,
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch((): { code?: string; message?: string; error?: { code?: string; message?: string } } => ({}));
    const code = body.code ?? body.error?.code;
    if (response.status === 503 && code === "routing_unavailable")
      throw new Error("Дорожный сервис временно недоступен. Перепланирование не выполнено.");
    throw new Error(body.message ?? body.error?.message ?? "Перепланирование временно недоступно.");
  }
  return response.json();
}
export async function buildRoadGeometry(
  planKind: PlanKind,
  engineerId: string,
  territory: Territory,
  trafficProfile: TrafficProfile,
  eventId?: string,
): Promise<RoadGeometryRoute> {
  const query = new URLSearchParams({ territory, traffic_profile: trafficProfile });
  if (eventId) query.set("event_id", eventId);
  const response = await authRequest(
    `/api/v1/plans/${planKind}/routes/${encodeURIComponent(engineerId)}/road-geometry?${query}`,
    { method: "POST" },
  );
  if (!response.ok) {
    const body = await response.json().catch((): { code?: string; message?: string } => ({}));
    if (response.status === 503 || body.code === "routing_unavailable") {
      throw new Error("Сервис дорожных маршрутов недоступен. Показана приближённая линия.");
    }
    throw new Error(body.message ?? `Не удалось построить маршрут: API ${response.status}.`);
  }
  return response.json();
}
type ApiError = { error?: { code?: string; message?: string } };
async function get<T>(path: string): Promise<T> {
  const response = await authRequest(path);
  if (!response.ok) {
    const body = await response.json().catch((): ApiError => ({}));
    if (response.status === 503 && body.error?.code === "plan_invariant_failed")
      throw new Error(
        "План временно недоступен: внутренняя проверка согласованности не пройдена.",
      );
    throw new Error(
      body.error?.message ?? `API вернул код ${response.status}.`,
    );
  }
  return response.json() as Promise<T>;
}
export function buildQuery(
  territory: Territory,
  trafficProfile: TrafficProfile,
  planKind?: PlanKind,
): string {
  const query = new URLSearchParams({
    territory,
    traffic_profile: trafficProfile,
  });
  if (planKind) query.set("plan_kind", planKind);
  return query.toString();
}
export function buildRequestsQuery(
  territory: Territory,
  trafficProfile: TrafficProfile,
  planKind: PlanKind,
  assignmentStatus: "assigned" | "unassigned" | undefined,
  limit: number,
  offset: number,
): string {
  const query = new URLSearchParams(
    buildQuery(territory, trafficProfile, planKind),
  );
  if (assignmentStatus) query.set("assignment_status", assignmentStatus);
  query.set("limit", String(limit));
  query.set("offset", String(offset));
  return query.toString();
}
export async function fetchDashboard(
  territory: Territory,
  trafficProfile: TrafficProfile,
  planKind: PlanKind,
): Promise<DashboardData> {
  const query = buildQuery(territory, trafficProfile);
  const [requests, plan, baseline, optimized, engineers, territories] =
    await Promise.all([
      get<{ items: DashboardData["requests"] }>(
        `/api/v1/requests?${buildQuery(territory, trafficProfile, planKind)}&limit=205`,
      ),
      get<DashboardData["plan"]>(`/api/v1/plans/${planKind}?${query}`),
      get<DashboardData["baseline"]>(
        `/api/v1/summary?${buildQuery(territory, trafficProfile, "baseline")}`,
      ),
      get<DashboardData["optimized"]>(
        `/api/v1/summary?${buildQuery(territory, trafficProfile, "optimized")}`,
      ),
      get<DashboardData["engineers"]>(
        `/api/v1/engineers?territory=${territory}`,
      ),
      get<DashboardData["territories"]>("/api/v1/territories"),
    ]);
  return {
    requests: requests.items,
    plan,
    baseline,
    optimized,
    engineers,
    territories,
  };
}
