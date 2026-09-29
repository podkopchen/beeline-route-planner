import type { DashboardData, RoadGeometryRoute } from "../types/api";

export function applyRoadGeometry(
  data: DashboardData,
  built: Record<string, RoadGeometryRoute>,
): DashboardData {
  return {
    ...data,
    plan: {
      ...data.plan,
      routes: data.plan.routes.map((route) => {
        const overlay = built[route.engineer_id];
        if (!overlay) return route;
        const legs = new Map(overlay.legs.map((leg) => [leg.sequence, leg]));
        return {
          ...route,
          stops: route.stops.map((stop) => {
            const leg = legs.get(stop.sequence);
            if (!leg) return stop;
            if (leg.source === "same_location") {
              return { ...stop, geometry: null, geometry_status: "same_location" as const, geometry_source: "same_location" as const };
            }
            return {
              ...stop,
              geometry: leg.geometry,
              geometry_status: "road" as const,
              geometry_source: leg.source,
              routing_warning: leg.source === "on_demand"
                ? "Дорожная геометрия построена при открытии маршрута; расписание и KPI плана не изменялись."
                : null,
            };
          }),
        };
      }),
    },
  };
}
