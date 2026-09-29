import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode, RefObject } from "react";
import { fetchExplanation } from "../api/client";
import type { DashboardData, PlanKind, Territory, TrafficProfile } from "../types/api";
const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleTimeString("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Moscow",
      })
    : "—";
export function RoutePanel({
  data,
  selectedRoute,
  onSelect,
  eventId,
  planKind = "optimized",
  trafficProfile = "standard",
  detailsOpen = true,
  onCloseDetails,
  territory = "east",
  activeTab,
  onTabChange,
  routeBuild,
  onBuildRoute,
}: {
  data?: DashboardData;
  selectedRoute?: string;
  onSelect: (id?: string) => void;
  eventId?: string;
  planKind?: PlanKind;
  trafficProfile?: TrafficProfile;
  detailsOpen?: boolean;
  onCloseDetails?: () => void;
  territory?: Territory;
  activeTab?: "routes" | "unassigned";
  onTabChange?: (tab: "routes" | "unassigned") => void;
  routeBuild?: { status: "idle" | "loading" | "ready" | "error"; message?: string };
  onBuildRoute?: () => void;
}) {
  const [localTab, setLocalTab] = useState<"routes" | "unassigned">("routes");
  const tab = activeTab ?? localTab;
  const setTab = (value: "routes" | "unassigned") => { setLocalTab(value); onTabChange?.(value); };
  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const expandButton = useRef<HTMLButtonElement>(null);
  const [explanation, setExplanation] = useState<{ title: string; summary: string; facts: { label_ru: string; value: string }[]; evidence_scope?: string }>();
  const [explanationError, setExplanationError] = useState<string>();
  const [selectedRequest, setSelectedRequest] = useState<string>();
  const explanationGeneration = useRef(0);
  useEffect(() => {
    explanationGeneration.current += 1;
    setSelectedRequest(undefined); setExplanation(undefined); setExplanationError(undefined);
    return () => { explanationGeneration.current += 1; };
  }, [selectedRoute, eventId, planKind, trafficProfile]);
  const loadExplanation = (requestId: string) => {
    const current = ++explanationGeneration.current;
    setSelectedRequest(requestId); setExplanation(undefined); setExplanationError(undefined);
    fetchExplanation(requestId, eventId, planKind, trafficProfile).then(value => {
      if (current === explanationGeneration.current) setExplanation(value);
    }).catch((error: unknown) => {
      if (current === explanationGeneration.current) setExplanationError(error instanceof Error ? error.message : "Ошибка объяснения");
    });
  };
  const route = data?.plan.routes.find(
    (item) => item.engineer_id === selectedRoute,
  );
  const requests = new Map(
    (data?.requests ?? []).map((item) => [item.request_id, item]),
  );
  const engineer = data?.engineers.find(
    (item) => item.engineer_id === selectedRoute,
  );
  const unassigned =
    data?.requests.filter((item) => item.assignment_status === "unassigned") ??
    [];
  const officeTerritory = new Map(data?.territories.map(item => [item.office_id, item.territory]));
  const territoryNames = { east: "Восток", southeast: "Юго-восток", southcenter: "Югоцентр" };
  const routes = data?.plan.routes.slice().sort((a, b) => `${officeTerritory.get(a.office_id) ?? ""}:${a.engineer_id}`.localeCompare(`${officeTerritory.get(b.office_id) ?? ""}:${b.engineer_id}`)) ?? [];
  const unassignedContent = <div className="unassigned-list">
    {unassigned.length === 0 && <p className="empty-state">Все заявки назначены. Проверять отказы не требуется.</p>}
    {unassigned.map(item => <article key={item.request_id}>
      <button onClick={() => loadExplanation(item.request_id)}>{item.request_id}</button>
      <span>{territoryNames[item.territory]} · {item.required_skills.join(", ")} · {item.priority === "normal" ? "Обычный приоритет" : item.priority}</span>
      {expanded && <><p className="request-address">{item.address}</p><dl className="request-facts"><div><dt>Временное окно</dt><dd>{time(item.window_start)}–{time(item.window_end)}</dd></div><div><dt>Обслуживание</dt><dd>{item.service_duration_min} мин</dd></div></dl></>}
      <p>{item.diagnostic?.text_ru}</p>
      <small>{item.diagnostic ? "Диагностика фиксированного плана" : "Причина отсутствует"}</small>
      {expanded && <button className="request-explain" onClick={() => loadExplanation(item.request_id)}>Почему не назначена</button>}
      {selectedRequest === item.request_id && <ExplanationView explanation={explanation} error={explanationError} onRetry={() => loadExplanation(item.request_id)} />}
    </article>)}
  </div>;
  return (
    <aside className={`route-panel ${collapsed ? "collapsed" : ""} ${route && detailsOpen && tab === "routes" ? "has-details" : ""}`} aria-label="Маршруты и заявки">
      <div className="route-panel-header"><div><small>План на смену</small><strong>{routes.length} маршрутов</strong></div><button className="panel-collapse" aria-label={collapsed ? "Развернуть панель маршрутов" : "Свернуть панель маршрутов"} aria-expanded={!collapsed} onClick={() => setCollapsed(value => !value)}><span>{collapsed ? "Маршруты" : "Свернуть"}</span><i /></button></div>
      <div className="route-panel-content" hidden={collapsed}><div className="route-tabs" role="tablist" aria-label="Раздел плана">
        <button
          role="tab" aria-selected={tab === "routes"}
          className={tab === "routes" ? "active" : ""}
          onClick={() => setTab("routes")}
        >
          Маршруты
        </button>
        <button
          role="tab" aria-selected={tab === "unassigned"}
          className={tab === "unassigned" ? "active" : ""}
          onClick={() => setTab("unassigned")}
        >
          Неназначенные
        </button>
      </div>
      {tab === "routes" && (
        <>
          <div className="route-list">
            {routes.map((item, index) => {
              const routeTerritory = officeTerritory.get(item.office_id);
              const previousTerritory = index > 0 ? officeTerritory.get(routes[index - 1].office_id) : undefined;
              return <div className="route-group" key={item.engineer_id}>
                {territory === "all" && routeTerritory !== previousTerritory && routeTerritory && <h3>{territoryNames[routeTerritory]}</h3>}
                <button
                  className={`route-row ${selectedRoute === item.engineer_id ? "selected" : ""}`}
                  aria-label={`Выбрать маршрут ${item.engineer_id}`}
                  aria-pressed={selectedRoute === item.engineer_id}
                  onClick={() =>
                    onSelect(
                      selectedRoute === item.engineer_id && detailsOpen
                        ? undefined
                        : item.engineer_id,
                    )
                  }
                >
                  <strong><i className={`route-indicator ${selectedRoute === item.engineer_id ? "selected" : ""}`} />{item.engineer_id}</strong>
                  <span>
                    {item.visit_count} виз. · {item.distance_km.toFixed(1)} км ·{" "}
                    {item.travel_minutes} мин
                  </span>
                  <small>Завершение {time(item.route_end)}</small>
                </button>
              </div>})}
          </div>
          {!data?.plan.routes.length && <p className="empty-state">В этом плане нет активных маршрутов.</p>}
          {route && detailsOpen && (
            <section className="drawer">
              <button
                className="close"
                onClick={() => onCloseDetails ? onCloseDetails() : onSelect(undefined)}
                aria-label="Закрыть детали маршрута"
              >
                ×
              </button>
              <h2>{route.engineer_id}</h2>
              <p>
                {engineer?.office_id ?? route.office_id} · смена{" "}
                {time(engineer?.shift_start ?? null)}–
                {time(engineer?.shift_end ?? null)}
              </p>
              <div className="badges">
                {!engineer && <span>Incident-only ресурс</span>}
                {engineer?.skills.map((skill) => (
                  <span key={skill}>{skill}</span>
                ))}
                <span>{engineer?.transport === "none" ? "Без автомобиля" : engineer?.transport === "car" ? "Автомобиль" : engineer?.transport}</span>
              </div>
              {routeBuild?.status === "loading" && <div className="route-build-status loading" role="status"><i />Строим выбранный маршрут по дорогам…</div>}
              {routeBuild?.status === "ready" && <div className="route-build-status ready" role="status"><i />Дорожная геометрия готова · порядок визитов и KPI не изменены</div>}
              {routeBuild?.status === "error" && <div className="route-build-status error" role="alert"><span>{routeBuild.message}</span>{onBuildRoute && <button onClick={onBuildRoute}>Повторить</button>}</div>}
              {engineer?.transport === "none" && <p className="routing-note">Линия по дорогам строится для наглядности по автомобильной сети. Расчётное время этого маршрута остаётся приближённым: пеший и общественный транспорт не моделируются.</p>}
              <strong>
                {route.visit_count} визитов · {route.distance_km.toFixed(1)} км
                · {route.travel_minutes} мин
              </strong>
              <ol className="timeline">
                {route.stops.map((stop) => {
                  const item = requests.get(stop.request_id);
                  return (
                    <li key={stop.request_id}>
                      <b>{stop.sequence}</b>
                      <div>
                        <button onClick={() => loadExplanation(stop.request_id)}>{stop.request_id}</button>
                        <span>{item?.address}</span>
                        {item?.mapStatus && <small className="stop-status">{item.mapStatus}</small>}
                        {item?.coordinates.latitude == null && <small>Координаты не переданы API — на карте только известные точки.</small>}
                        <small>
                          Окно {time(item?.window_start ?? null)}–
                          {time(item?.window_end ?? null)} · приб.{" "}
                          {time(stop.arrival)} · работа{" "}
                          {time(stop.service_start)}–{time(stop.service_end)}
                        </small>
                        <small>
                          {stop.geometry_status === "road" && stop.geometry?.length ? (stop.geometry_source === "on_demand" ? "По дорогам (построено при открытии)" : "По дорогам (кэш)") : "Приближённая линия"}: {stop.adjusted_travel_minutes ?? stop.travel_minutes} мин ·
                          {stop.base_travel_minutes !== undefined && ` (база ${stop.base_travel_minutes})`} · {stop.distance_km.toFixed(1)} км · ожидание{" "}
                          {stop.waiting_minutes} мин · работа{" "}
                          {item?.service_duration_min} мин
                        </small>
                        {stop.routing_warning ? <small>{stop.routing_warning}</small> : stop.routing_source === "fallback" && <small>Расчётный путь: дорожная геометрия недоступна.</small>}
                      </div>
                    </li>
                  );
                })}
              </ol>
              {selectedRequest && <ExplanationView explanation={explanation} error={explanationError} onRetry={() => loadExplanation(selectedRequest)} />}
              <p className="end-note">
                Маршрут заканчивается на последней заявке; возврат в офис не
                добавляется.
              </p>
            </section>
          )}
        </>
      )}
      {tab === "unassigned" && (
        <><div className="unassigned-toolbar"><span>{unassigned.length} заявок</span><button ref={expandButton} onClick={() => setExpanded(true)}>Открыть подробнее ↗</button></div>
          {!expanded && unassignedContent}
          {expanded && <ExpandedRequests count={unassigned.length} returnFocus={expandButton} onClose={() => setExpanded(false)}>{unassignedContent}</ExpandedRequests>}
        </>
      )}
      </div>
    </aside>
  );
}

function ExpandedRequests({ count, onClose, children, returnFocus }: { count: number; onClose: () => void; children: ReactNode; returnFocus: RefObject<HTMLButtonElement> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    const opener = returnFocus.current;
    element?.showModal();
    return () => { element?.close(); opener?.focus(); };
  }, [returnFocus]);
  return createPortal(<dialog ref={dialog} className="requests-dialog" aria-labelledby="requests-dialog-title" onCancel={event => { event.preventDefault(); onClose(); }}><div className="panel-heading"><div><small>Проверка назначений · {count} заявок</small><h2 id="requests-dialog-title">Неназначенные заявки</h2></div><button autoFocus onClick={onClose} aria-label="Закрыть подробности неназначенных заявок">Закрыть ×</button></div><p className="requests-dialog-intro">Адрес, временное окно и проверенная причина отказа. Выберите заявку, чтобы увидеть факты решения.</p>{children}</dialog>, document.body);
}

function ExplanationView({ explanation, error, onRetry }: { explanation?: { title: string; summary: string; facts: { label_ru: string; value: string }[]; evidence_scope?: string }; error?: string; onRetry: () => void }) {
  return <section className="explanation"><h3>Почему это решение</h3>{!explanation && !error && <p>Загружаем объяснение…</p>}{error && <p>{error} <button onClick={onRetry}>Повторить</button></p>}{explanation && <><p>{explanation.summary}</p><details><summary>Факты</summary>{explanation.facts.map((fact) => <div key={fact.label_ru}>{fact.label_ru}: {fact.value}</div>)}</details>{explanation.evidence_scope && <small>{explanation.evidence_scope}</small>}</>}</section>;
}
