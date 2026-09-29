import { useEffect, useMemo, useRef, useState } from "react";
import type { Map as LibreMap, GeoJSONSource, Marker, Popup } from "maplibre-gl";
import type { DashboardData, Filter, Territory, TrafficProfile } from "../types/api";
import { sceneFor, trafficColors } from "../map/scene";
import { directionArrows } from "../map/direction";
import { OfflineMap } from "./OfflineMap";
import "maplibre-gl/dist/maplibre-gl.css";

export const MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
type MapDiagnosticReason = "style_timeout" | "style_load_failed" | "tile_source_failed" | "webgl_unavailable" | "map_init_failed" | "container_unavailable";

export function DispatcherMap({ data, filter, loading, territory = "east", selectedRoute, trafficProfile = "standard", onSelect }: { data?: DashboardData; filter: Filter; loading: boolean; territory?: Territory; selectedRoute?: string; trafficProfile?: TrafficProfile; onSelect?: (id: string) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LibreMap>();
  const engine = useRef<typeof import("maplibre-gl")>();
  const buildingLayers = useRef<string[]>([]);
  const loggedFallbackReasons = useRef(new Set<MapDiagnosticReason>());
  const [state, setState] = useState<"loading" | "online" | "offline">("loading");
  const [diagnosticReason, setDiagnosticReason] = useState<MapDiagnosticReason>();
  const [mode, setMode] = useState<"2D" | "3D">("2D");
  const [buildings, setBuildings] = useState(false);
  const scene = useMemo(() => sceneFor(data, filter, selectedRoute, trafficProfile, territory), [data, filter, selectedRoute, trafficProfile, territory]);
  const [selection, setSelection] = useState<{ scene: typeof scene; id: string }>();
  const focusedLeg = selection?.scene === scene ? scene.legs.find(leg => leg.id === selection.id) : undefined;
  useEffect(() => {
    let disposed = false, failed = false, styleLoaded = false;
    let pendingFailure: MapDiagnosticReason | undefined;
    let map: LibreMap | undefined;
    const fallback = (reason: MapDiagnosticReason) => { if (disposed || failed) return; failed = true; if (!loggedFallbackReasons.current.has(reason)) { loggedFallbackReasons.current.add(reason); console.warn(`[RouteFlow map] fallback: ${reason}`); } clearTimeout(timer); observer?.disconnect(); setDiagnosticReason(reason); setState("offline"); setMode("2D"); mapRef.current = undefined; map?.remove(); };
    const timer = window.setTimeout(() => fallback(pendingFailure ?? "style_timeout"), 30000);
    let observer: ResizeObserver | undefined;
    void import("maplibre-gl").then(lib => {
      if (disposed || failed) return;
      if (!host.current || host.current.clientWidth < 1 || host.current.clientHeight < 1) { fallback("container_unavailable"); return; }
      engine.current = lib;
      try {
        map = new lib.Map({ container: host.current, style: MAP_STYLE_URL, center: [37.62, 55.75], zoom: 8, pitch: 0, bearing: 0, attributionControl: false });
        mapRef.current = map;
        map.on("error", () => {
          // MapLibre can emit recoverable sprite/glyph/tile errors before `load`.
          // Preserve the map until the load deadline instead of hiding a usable basemap.
          if (!styleLoaded) pendingFailure = "style_load_failed";
        });
        map.on("webglcontextlost", () => fallback("webgl_unavailable"));
        map.on("load", () => {
          if (failed || disposed || !map) return;
          try {
          styleLoaded = true; pendingFailure = undefined; clearTimeout(timer); setDiagnosticReason(undefined);
          const style = map.getStyle();
          const buildingSource = Boolean(style.sources.openmaptiles && style.layers.some(layer => "source-layer" in layer && layer.source === "openmaptiles" && layer["source-layer"] === "building"));
          buildingLayers.current = style.layers.filter(layer => layer.type === "fill-extrusion" && "source-layer" in layer && layer.source === "openmaptiles" && layer["source-layer"] === "building").map(layer => layer.id);
          if (buildingSource && !buildingLayers.current.length) {
            map.addLayer({ id: "routeflow-buildings", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building", minzoom: 13, layout: { visibility: "none" }, paint: { "fill-extrusion-color": "#b5bec4", "fill-extrusion-height": ["coalesce", ["get", "render_height"], ["get", "height"], 0], "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0], "fill-extrusion-opacity": .55 } });
            buildingLayers.current = ["routeflow-buildings"];
          }
          buildingLayers.current.forEach(id => map?.setLayoutProperty(id, "visibility", "none"));
          // Keep the demo basemap quiet behind application routes.
          if (map.getLayer("countries-fill")) map.setPaintProperty("countries-fill", "fill-color", "#f0f2ec");
          map.addSource("routeflow-legs", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({ id: "routeflow-outline", type: "line", source: "routeflow-legs", filter: ["all", ["==", ["get", "selected"], true], ["==", ["get", "routingSource"], "road"]], paint: { "line-color": "#ffffff", "line-width": 11, "line-opacity": .85 }, layout: { "line-cap": "round", "line-join": "round" } });
          map.addLayer({ id: "routeflow-lines", type: "line", source: "routeflow-legs", filter: ["==", ["get", "routingSource"], "road"], paint: { "line-color": ["get", "color"], "line-width": ["case", ["get", "selected"], 7, 1.5], "line-opacity": ["case", ["get", "selected"], 1, .2] }, layout: { "line-cap": "round", "line-join": "round" } });
          map.addLayer({ id: "routeflow-fallback", type: "line", source: "routeflow-legs", filter: ["==", ["get", "routingSource"], "fallback"], paint: { "line-color": "#71808b", "line-width": ["case", ["get", "selected"], 2, 1], "line-opacity": .75, "line-dasharray": [2, 2] }, layout: { "line-cap": "round", "line-join": "round" } });
          map.addControl(new lib.NavigationControl(), "bottom-left");
          map.addSource("routeflow-focus", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({ id: "routeflow-focus-outline", type: "line", source: "routeflow-focus", paint: { "line-color": "#ffffff", "line-width": 12 }, layout: { "line-cap": "round", "line-join": "round" } });
          map.addLayer({ id: "routeflow-focus-line", type: "line", source: "routeflow-focus", paint: { "line-color": ["get", "color"], "line-width": 7 }, layout: { "line-cap": "round", "line-join": "round" } });
          map.addSource("routeflow-arrows", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({ id: "routeflow-arrows", type: "line", source: "routeflow-arrows", paint: { "line-color": "#ffffff", "line-width": 2.5 }, layout: { "line-cap": "round", "line-join": "round" } });
          setBuildings(buildingLayers.current.length > 0); setState("online");
          } catch { fallback("map_init_failed"); }
        });
        observer = new ResizeObserver(() => map?.resize()); observer.observe(host.current);
      } catch { fallback("map_init_failed"); }
    }).catch(() => fallback("map_init_failed"));
    return () => { disposed = true; clearTimeout(timer); observer?.disconnect(); if (!failed) map?.remove(); mapRef.current = undefined; };
  }, []);
  useEffect(() => {
    const map = mapRef.current, lib = engine.current;
    if (state !== "online" || !map || !lib) return;
    (map.getSource("routeflow-legs") as GeoJSONSource).setData({ type: "FeatureCollection", features: scene.legs.map(leg => ({ type: "Feature", geometry: { type: "LineString", coordinates: leg.positions }, properties: { id: leg.id, selected: leg.selected, color: leg.selected ? trafficColors[leg.level] : "#6d7c86", detail: leg.detail, engineer: leg.engineer, routingSource: leg.routingSource } })) });
    const markers: Marker[] = [], popups: Popup[] = [];
    for (const point of scene.points) {
      const element = document.createElement("button"); element.className = `map-marker ${point.kind} ${point.sequence ? "numbered" : ""}`; element.textContent = point.label; element.setAttribute("aria-label", point.id); element.title = point.detail;
      element.onclick = () => { if (point.engineer) onSelect?.(point.engineer); };
      const popup = new lib.Popup({ offset: 15 }).setText(point.detail); popups.push(popup);
      markers.push(new lib.Marker({ element }).setLngLat(point.displayPosition).setPopup(popup).addTo(map));
    }
    const hover = new lib.Popup({ closeButton: false }); popups.push(hover);
    const onHover = (event: import("maplibre-gl").MapLayerMouseEvent) => { const properties = event.features?.[0]?.properties; if (properties) hover.setLngLat(event.lngLat).setText(String(properties.detail)).addTo(map); };
    const onLeave = () => { hover.remove(); };
    const onClick = (event: import("maplibre-gl").MapLayerMouseEvent) => {
      const properties = event.features?.[0]?.properties;
      if (!properties) return;
      hover.remove();
      const id = String(properties.id);
      setSelection(previous => previous?.scene === scene && previous.id === id ? undefined : { scene, id });
      if (properties.engineer !== selectedRoute) onSelect?.(String(properties.engineer));
    };
    for (const layer of ["routeflow-lines", "routeflow-fallback"]) {
      map.on("mousemove", layer, onHover); map.on("mouseleave", layer, onLeave); map.on("click", layer, onClick);
    }
    if (scene.focusPositions.length) {
      const bounds = new lib.LngLatBounds(); scene.focusPositions.forEach(point => bounds.extend(point));
      const tokens = getComputedStyle(document.documentElement);
      const left = parseFloat(tokens.getPropertyValue("--left")) || 288;
      const right = parseFloat(tokens.getPropertyValue("--right")) || 342;
      // Frame the route in the actual free map canvas between the two side panels.
      map.fitBounds(bounds, { padding: { top: 150, right: right + 42, bottom: 210, left: left + 42 }, maxZoom: selectedRoute ? 14 : 10, duration: 600, bearing: map.getBearing(), pitch: map.getPitch() });
    }
    return () => { markers.forEach(marker => marker.remove()); popups.forEach(popup => popup.remove()); for (const layer of ["routeflow-lines", "routeflow-fallback"]) { map.off("mousemove", layer, onHover); map.off("mouseleave", layer, onLeave); map.off("click", layer, onClick); } };
  }, [scene, state, onSelect, selectedRoute]);
  useEffect(() => {
    const map = mapRef.current, lib = engine.current;
    if (state !== "online" || !map || !lib) return;
    map.setPaintProperty("routeflow-lines", "line-opacity", focusedLeg ? .16 : ["case", ["get", "selected"], 1, .2]);
    map.setPaintProperty("routeflow-outline", "line-opacity", focusedLeg ? .1 : .85);
    map.setPaintProperty("routeflow-fallback", "line-opacity", focusedLeg ? .2 : .75);
    // Never promote missing road geometry to a solid road-looking line.
    (map.getSource("routeflow-focus") as GeoJSONSource).setData({ type: "FeatureCollection", features: focusedLeg?.routingSource === "road" ? [{ type: "Feature", properties: { color: trafficColors[focusedLeg.level] }, geometry: { type: "LineString", coordinates: focusedLeg.positions } }] : [] });
    let popup: Popup | undefined;
    if (focusedLeg) {
      popup = new lib.Popup({ closeButton: false, offset: 12 }).setLngLat(focusedLeg.positions[Math.floor(focusedLeg.positions.length / 2)]).setText(`${focusedLeg.sequence === 1 ? "Офис" : `Остановка ${focusedLeg.sequence - 1}`} → Остановка ${focusedLeg.sequence}\n${focusedLeg.detail}`).addTo(map);
    }
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const draw = () => {
      const size = Math.max(3, 5 * 156543 * Math.cos(55.75 * Math.PI / 180) / 2 ** map.getZoom());
      (map.getSource("routeflow-arrows") as GeoJSONSource).setData(directionArrows(focusedLeg ? [focusedLeg] : scene.legs, reducedMotion ? 0 : performance.now() / 3500, size));
    };
    draw();
    const timer = reducedMotion ? undefined : window.setInterval(draw, 100);
    return () => { window.clearInterval(timer); popup?.remove(); };
  }, [scene, state, focusedLeg]);
  useEffect(() => {
    const map = mapRef.current;
    if (state !== "online" || !map) return;
    map.easeTo({ pitch: mode === "3D" ? 60 : 0, bearing: mode === "3D" ? -20 : 0, duration: 700 });
    buildingLayers.current.forEach(id => { if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", mode === "3D" ? "visible" : "none"); });
  }, [mode, state]);
  return <section className="map-panel" aria-label="Карта маршрутов">
    <div className="maplibre-host" ref={host} style={{ visibility: state === "online" ? "visible" : "hidden" }} />
    {state === "online" && <div className="map-leg-picker"><label>Участок <select aria-label="Выбрать участок маршрута" value={focusedLeg?.id ?? ""} onChange={event => setSelection(event.target.value ? { scene, id: event.target.value } : undefined)}><option value="">Все участки · стрелки →</option>{scene.legs.filter(leg => leg.selected).map(leg => <option key={leg.id} value={leg.id}>{leg.sequence === 1 ? "Офис" : leg.sequence - 1} → {leg.sequence}</option>)}</select></label>{focusedLeg && <button onClick={() => setSelection(undefined)}>Снять выделение</button>}</div>}
    {state !== "online" && <OfflineMap key={JSON.stringify([scene.points.map(point => point.position), trafficProfile])} scene={scene} onSelect={onSelect} />}
    {import.meta.env.DEV && <div className="map-dev-diagnostic" aria-label="Диагностика подложки"><span>Подложка: {state === "online" ? "online" : state === "offline" ? "offline" : "loading"}</span><span>Причина: {diagnosticReason ?? "—"}</span></div>}
    <div className="map-mode" role="group" aria-label="Режим карты"><span>Карта:</span>{(["2D", "3D"] as const).map(value => <button key={value} aria-label={`Карта ${value}`} aria-pressed={mode === value} disabled={value === "3D" && state === "offline"} title={state === "offline" ? "3D доступен при загрузке онлайн-карты" : value === "3D" && state === "online" && !buildings ? "Наклон камеры; style не содержит зданий" : `Переключить в ${value}`} onClick={() => setMode(value)}>{value}</button>)}<span>{state === "offline" ? "Офлайн-схема" : state === "loading" ? "Загрузка подложки…" : "OpenFreeMap"}</span>{state === "offline" && <small>3D доступен при загрузке онлайн-карты</small>}{state === "online" && mode === "3D" && !buildings && <small>Здания отсутствуют в style</small>}</div>
    <div className="map-legend" aria-label="Легенда карты"><strong>Сценарная загруженность</strong><div><i className="free" /> свободно <i className="moderate" /> умеренно <i className="peak" /> пик</div><b>Модельная оценка, не текущие пробки</b><small>⌂ офис · ● заявка · <span className="coral">! неназначена</span> · ≈ приближённо</small><small>Линия показывает последовательность визитов; не навигация по улицам.</small></div>
    {scene.overview && <div className="overview-note">Обзор трёх территорий · выберите маршрут для фокуса</div>}
    {loading && <div className="map-notice" role="status">Обновление плана…</div>}
    {!scene.points.length && !loading && <div className="map-notice">Нет координат для отображения</div>}
    {scene.missing.length > 0 && <div className="map-missing" role="status">Нет координат в API: {scene.missing.join(", ")}. Расписание доступно в маршруте.</div>}
    <div className="map-attribution">© OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors</div>
  </section>;
}
