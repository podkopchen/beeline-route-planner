import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { applyReplan, buildRoadGeometry, fetchDashboard } from "./api/client";
import { ControlBar } from "./components/ControlBar";
import { DispatcherMap } from "./components/DispatcherMap";
import { KpiStrip } from "./components/KpiStrip";
import { RoutePanel } from "./components/RoutePanel";
import { Icon } from "./components/Icon";
import { BeeLogo } from "./components/BeeLogo";
import { replanView } from "./map/replanView";
import { applyRoadGeometry } from "./map/roadGeometry";
import type { AuthUser, DashboardData, Filter, PlanKind, ReplanResponse, RoadGeometryRoute, Territory, TrafficProfile } from "./types/api";

type RouteBuildState = { status: "idle" | "loading" | "ready" | "error"; message?: string };

export default function App({ user = { username: "dispatcher", display_name: "Диспетчер смены", role: "dispatcher" }, onLogout }: { user?: AuthUser; onLogout?: () => Promise<void> }) {
  const [territory, setTerritory] = useState<Territory>("east");
  const [trafficProfile, setTrafficProfile] = useState<TrafficProfile>("standard");
  const [filter, setFilter] = useState<Filter>("all");
  const [planKind, setPlanKind] = useState<PlanKind>("optimized");
  const [selectedRoute, setSelectedRoute] = useState<string>();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(true);
  const [panelTab, setPanelTab] = useState<"routes" | "unassigned">("routes");
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{ data?: DashboardData; error?: string; loading: boolean }>({ loading: true });
  const [scenario, setScenario] = useState<ReplanResponse>();
  const [simulating, setSimulating] = useState(false);
  const [scenarioError, setScenarioError] = useState<string>();
  const [roadGeometry, setRoadGeometry] = useState<Record<string, RoadGeometryRoute>>({});
  const [routeBuild, setRouteBuild] = useState<Record<string, RouteBuildState>>({});
  const generation = useRef(0);
  useEffect(() => {
    const current = ++generation.current;
    setState({ loading: true }); setScenario(undefined); setScenarioError(undefined); setSimulating(false); setDrawerOpen(false); setSelectedRoute(undefined); setRoadGeometry({}); setRouteBuild({});
    fetchDashboard(territory, trafficProfile, planKind).then(data => {
      if (current === generation.current) setState({ data: { ...data, territories: data.territories.filter(item => territory === "all" || item.territory === territory) }, loading: false });
    }).catch((error: unknown) => {
      if (current === generation.current) setState({ loading: false, error: error instanceof Error ? error.message : "Не удалось получить данные API." });
    });
    return () => { generation.current = current + 1; };
  }, [territory, trafficProfile, planKind, revision]);
  const planData = useMemo(() => state.data && scenario ? replanView(state.data, scenario) : state.data, [state.data, scenario]);
  const data = useMemo(() => planData ? applyRoadGeometry(planData, roadGeometry) : undefined, [planData, roadGeometry]);
  const activeRoute = data?.plan.routes.find(route => route.engineer_id === selectedRoute)?.engineer_id ?? (territory === "all" ? undefined : data?.plan.routes.find(route => route.stops.length)?.engineer_id);
  const selectRoute = useCallback((id?: string) => { setSelectedRoute(id); setDrawerOpen(Boolean(id)); setPanelTab("routes"); }, []);
  const buildSelectedRoadRoute = useCallback((engineerId: string) => {
    const current = generation.current;
    setRouteBuild(previous => ({ ...previous, [engineerId]: { status: "loading" } }));
    buildRoadGeometry(planKind, engineerId, territory, trafficProfile, scenario ? "event-east-urgent-1430" : undefined)
      .then(result => {
        if (current !== generation.current) return;
        setRoadGeometry(previous => ({ ...previous, [engineerId]: result }));
        setRouteBuild(previous => ({ ...previous, [engineerId]: { status: "ready" } }));
      })
      .catch((error: unknown) => {
        if (current !== generation.current) return;
        setRouteBuild(previous => ({ ...previous, [engineerId]: { status: "error", message: error instanceof Error ? error.message : "Не удалось построить дорожный маршрут." } }));
      });
  }, [planKind, territory, trafficProfile, scenario]);
  useEffect(() => {
    if (!drawerOpen || !activeRoute || !planData) return;
    const route = planData.plan.routes.find(item => item.engineer_id === activeRoute);
    if (!route || route.stops.every(stop => stop.geometry_status === "road" || stop.geometry_status === "same_location")) return;
    if ((routeBuild[activeRoute]?.status ?? "idle") !== "idle") return;
    buildSelectedRoadRoute(activeRoute);
  }, [activeRoute, drawerOpen, planData, routeBuild, buildSelectedRoadRoute]);
  const simulate = () => {
    const current = generation.current;
    setSimulating(true); setScenarioError(undefined);
    applyReplan("event-east-urgent-1430", trafficProfile).then(result => {
      if (current !== generation.current) return;
      // Ignore geometry requests still in flight for the canonical plan.
      generation.current += 1;
      setScenario(result); setSimulating(false); setRoadGeometry({}); setRouteBuild({});
      setPanelTab("routes");
      setSelectedRoute(result.diff.activated_reserve_engineer_id ?? undefined); setDrawerOpen(true);
    }).catch((error: unknown) => {
      if (current !== generation.current) return;
      setSimulating(false); setScenarioError(error instanceof Error ? error.message : "Ошибка перепланирования");
    });
  };
  const summary = data?.plan.summary;
  const base = state.data?.plan.summary;
  const signed = (value: number) => `${value > 0 ? "+" : ""}${value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}`;
  return <main className="app-shell">
    <header className="app-header"><div className="brand"><BeeLogo size={38} className="header-bee-logo" /><div><strong>Route<span>Flow</span></strong><small>УПРАВЛЕНИЕ ВЫЕЗДАМИ</small></div></div>
      <nav className="primary-nav" aria-label="Навигация диспетчера">
        <button aria-pressed={!comparisonOpen} onClick={() => setComparisonOpen(false)}><Icon name="map" />Карта маршрутов</button>
        <button aria-pressed={comparisonOpen} onClick={() => setComparisonOpen(value => !value)}><Icon name="chart" />Сравнение планов</button>
      </nav><div className="account-menu"><button className="account-trigger" aria-expanded={accountOpen} onClick={() => setAccountOpen(value => !value)}><span className="operator-avatar">{user.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.display_name}</strong><small>Билайн Бизнес</small></div><i /></button>{accountOpen && <div className="account-popover"><div><BeeLogo size={38} /><p><strong>{user.display_name}</strong><span>@{user.username} · Диспетчер</span></p></div><button onClick={() => { setAccountOpen(false); void onLogout?.(); }}>Выйти из аккаунта <span>↗</span></button></div>}</div></header>
    <section className="workspace" aria-label="Диспетчерская карта">
      <DispatcherMap data={data} filter={filter} loading={state.loading} territory={territory} selectedRoute={activeRoute} trafficProfile={trafficProfile} onSelect={selectRoute} />
      <div className="left-stack">
      <div className={`floating-controls ${controlsOpen ? "expanded" : "collapsed"}`}>
        <div className="panel-heading"><div><small>Управление планом</small><strong>Параметры смены</strong></div><button className="panel-collapse" aria-label={controlsOpen ? "Свернуть управление планом" : "Развернуть управление планом"} aria-expanded={controlsOpen} onClick={() => setControlsOpen(value => !value)}><span>{controlsOpen ? "Свернуть" : "Настроить"}</span><i /></button></div>
        <div className="collapsible-content" hidden={!controlsOpen}><ControlBar territory={territory} trafficProfile={trafficProfile} planKind={planKind} loading={state.loading} error={Boolean(state.error)} onTerritory={setTerritory} onTraffic={setTrafficProfile} onPlanKind={setPlanKind} />
          <label className="point-filter"><span>Заявки на карте</span><select aria-label="Статус заявок на карте" value={filter} onChange={event => setFilter(event.target.value as Filter)}><option value="all">Все</option><option value="assigned">Назначенные</option><option value="unassigned">Неназначенные</option></select></label></div>
      </div>
      <section className="current-kpi" aria-label="Метрики выбранного плана"><h2>План на смену</h2>
        <div><strong>{summary?.assigned_count ?? "—"}</strong><span>назначено</span></div><div><strong>{summary?.unassigned_count ?? "—"}</strong><span>не назначено</span></div><div><strong>{summary?.active_engineer_count ?? "—"}</strong><span>инженеров</span></div><div><strong>{summary?.total_distance_km.toFixed(1) ?? "—"}</strong><span>км · без возврата</span></div>
        <button className="comparison-trigger" onClick={() => setComparisonOpen(value => !value)}><Icon name="chart" />Сравнить с baseline<Icon name="arrow" /></button>
      </section>
      {(state.loading || state.error) && <div className="api-notice" role="status">{state.loading ? "Загружаем план…" : <>{state.error} <button onClick={() => setRevision(value => value + 1)}>Повторить</button></>}</div>}
      {territory === "east" && planKind === "optimized" && <section className="event-simulation" aria-label="Симуляция событий">
        <div className="event-heading"><span className="event-icon">!</span><div><strong>Симуляция события</strong><small>Synthetic event · не live-мониторинг</small></div></div>
        {!scenario ? <button disabled={simulating} onClick={simulate}>{simulating ? "Применяем сценарий…" : "Срочная авария · 14:30"}</button> : <>
          {scenario.diff.emergency_reserve_activated && <strong className="reserve-badge">Аварийный резерв активирован</strong>}
          <details open><summary>Изменение плана · {scenario.diff.committed_visit_count} зафиксировано</summary><p>Новые: {scenario.diff.added_urgent_request_ids?.length ?? 0} · сняты: {scenario.diff.cancelled_request_ids?.length ?? 0} · переназначены: {scenario.diff.reassigned?.length ?? 0}</p><p>Затронуто инженеров: {scenario.diff.affected_engineer_ids?.length ?? 0}</p>
            {summary && base && <p>Назначено {signed(summary.assigned_count - base.assigned_count)} · инженеры {signed(summary.active_engineer_count - base.active_engineer_count)} · {signed(summary.total_distance_km - base.total_distance_km)} км · дорога {signed(summary.total_travel_minutes - base.total_travel_minutes)} мин</p>}
            {scenario.diff.activated_reserve_engineer_id && <small>Новый ресурс: {scenario.diff.activated_reserve_engineer_id}</small>}
          </details>
          <button onClick={() => { setScenario(undefined); setRoadGeometry({}); setRouteBuild({}); setDrawerOpen(false); setSelectedRoute(undefined); setRevision(value => value + 1); }}>Сбросить сценарий</button>
        </>}
        {scenarioError && <div role="alert">{scenarioError} <button onClick={simulate}>Повторить</button></div>}
      </section>}
      <div className="data-note"><span />Демонстрационные данные · офлайн-расчёт</div>
      </div>
      <RoutePanel key={`${territory}:${trafficProfile}:${planKind}:${Boolean(scenario)}`} activeTab={panelTab} onTabChange={setPanelTab} territory={territory} planKind={planKind} trafficProfile={trafficProfile} data={data} selectedRoute={activeRoute} onSelect={selectRoute} detailsOpen={drawerOpen} onCloseDetails={() => setDrawerOpen(false)} eventId={scenario ? "event-east-urgent-1430" : undefined} routeBuild={activeRoute ? routeBuild[activeRoute] : undefined} onBuildRoute={activeRoute ? () => buildSelectedRoadRoute(activeRoute) : undefined} />
      {comparisonOpen && <section className="comparison-overlay" role="dialog" aria-modal="false" aria-label="Сравнение планов" onKeyDown={event => { if (event.key === "Escape") setComparisonOpen(false); }}><div className="panel-heading"><div><small>Эффективность планирования</small><strong>Сравнение планов</strong></div><button autoFocus className="close" aria-label="Закрыть сравнение" onClick={() => setComparisonOpen(false)}>×</button></div><KpiStrip data={state.data} /></section>}
    </section>
  </main>;
}
