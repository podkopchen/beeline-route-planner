import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { dashboard } from "../test/fixtures";
import { DispatcherMap, MAP_STYLE_URL } from "./DispatcherMap";

const mock = vi.hoisted(() => ({ handlers: new Map<string, () => void>(), layerHandlers: new Map<string, (event: unknown) => void>(), constructor: vi.fn(), setData: vi.fn(), fitBounds: vi.fn(), easeTo: vi.fn(), addLayer: vi.fn(), setPaintProperty: vi.fn(), setLayoutProperty: vi.fn(), remove: vi.fn(), buildings: false, nativeExtrusion: false, autoLoad: true }));
vi.mock("maplibre-gl", () => {
  class Map {
    constructor(options: unknown) { mock.constructor(options); queueMicrotask(() => { if (mock.autoLoad) mock.handlers.get("load")?.(); }); }
    on(event: string, fn: unknown, handler?: (event: unknown) => void) { if (typeof fn === "function") mock.handlers.set(event, fn as () => void); if (typeof fn === "string" && handler) mock.layerHandlers.set(`${event}:${fn}`, handler); return this; }
    off() { return this; }
    getStyle() { return { sources: mock.buildings ? { openmaptiles: {} } : {}, layers: mock.buildings ? [{ id: mock.nativeExtrusion ? "building-3d" : "building", type: mock.nativeExtrusion ? "fill-extrusion" : "fill", source: "openmaptiles", "source-layer": "building" }] : [] }; }
    getLayer(id: string) { return (id === "routeflow-buildings" && mock.buildings) || (id === "building-3d" && mock.nativeExtrusion); }
    getSource() { return { setData: mock.setData }; }
    addSource() {}
    addLayer = mock.addLayer;
    addControl() {}
    fitBounds = mock.fitBounds;
    easeTo = mock.easeTo;
    setLayoutProperty = mock.setLayoutProperty;
    setPaintProperty = mock.setPaintProperty;
    getZoom() { return 14; }
    getBearing() { return 0; }
    getPitch() { return 0; }
    resize() {}
    remove = mock.remove;
  }
  class Popup { setText() { return this; } setLngLat() { return this; } addTo() { return this; } remove() {} }
  class Marker { setLngLat() { return this; } setPopup() { return this; } addTo() { return this; } remove() {} }
  return { Map, Popup, Marker, NavigationControl: class {}, LngLatBounds: class { extend() { return this; } } };
});
beforeEach(() => {
  mock.handlers.clear(); mock.layerHandlers.clear(); mock.buildings = false; mock.nativeExtrusion = false; mock.autoLoad = true;
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 1366 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 712 });
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("Network forbidden in map tests"); }));
});
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it("switches 2D/3D camera without changing route or its API geometry", async () => {
  const select = vi.fn();
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" onSelect={select} />);
  await screen.findByText("OpenFreeMap");
  expect(mock.constructor).toHaveBeenCalledWith(expect.objectContaining({ style: MAP_STYLE_URL }));
  expect(MAP_STYLE_URL).toBe("https://tiles.openfreemap.org/styles/liberty");
  const previous = mock.setData.mock.calls.at(-1);
  fireEvent.click(screen.getByRole("button", { name: "Карта 3D" }));
  expect(mock.easeTo).toHaveBeenLastCalledWith({ pitch: 60, bearing: -20, duration: 700 });
  expect(screen.getByText("Здания отсутствуют в style")).toBeTruthy();
  expect(mock.setData.mock.calls.at(-1)).toEqual(previous);
  expect(select).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Карта 2D" }));
  expect(mock.easeTo).toHaveBeenLastCalledWith({ pitch: 0, bearing: 0, duration: 700 });
  expect(fetch).not.toHaveBeenCalled();
});
it("outlines only road geometry and renders fallback using valid dashed paint", async () => {
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await screen.findByText("OpenFreeMap");
  const layers = mock.addLayer.mock.calls.map(([layer]) => layer);
  expect(layers.find(layer => layer.id === "routeflow-outline").filter).toEqual(["all", ["==", ["get", "selected"], true], ["==", ["get", "routingSource"], "road"]]);
  const fallback = layers.find(layer => layer.id === "routeflow-fallback");
  expect(fallback.paint["line-dasharray"]).toEqual([2, 2]);
  expect(fallback.layout).not.toHaveProperty("line-dasharray");
});
it("adds extrusions only when style actually contains building data", async () => {
  mock.buildings = true;
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await screen.findByText("OpenFreeMap");
  expect(mock.addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: "routeflow-buildings", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building" }));
  fireEvent.click(screen.getByRole("button", { name: "Карта 3D" }));
  expect(mock.setLayoutProperty).toHaveBeenLastCalledWith("routeflow-buildings", "visibility", "visible");
});
it("reuses a native OpenFreeMap building extrusion instead of adding a duplicate", async () => {
  mock.buildings = true; mock.nativeExtrusion = true;
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await screen.findByText("OpenFreeMap");
  expect(mock.addLayer).not.toHaveBeenCalledWith(expect.objectContaining({ id: "routeflow-buildings" }));
  expect(mock.setLayoutProperty).toHaveBeenCalledWith("building-3d", "visibility", "none");
  fireEvent.click(screen.getByRole("button", { name: "Карта 3D" }));
  expect(mock.setLayoutProperty).toHaveBeenLastCalledWith("building-3d", "visibility", "visible");
});
it("falls back after style error with real office, route, stops, disabled 3D and no fallback network", async () => {
  mock.autoLoad = false; vi.useFakeTimers();
  const data = { ...dashboard, territories: [{ territory: "east" as const, office_id: "office-east", office_coordinates: dashboard.requests[1].coordinates }] };
  render(<DispatcherMap data={data} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByText("Загрузка подложки…")).toBeTruthy();
  act(() => mock.handlers.get("error")?.());
  expect(screen.queryByText("Офлайн-схема")).toBeNull();
  act(() => vi.advanceTimersByTime(30000));
  expect(screen.getByText("Офлайн-схема")).toBeTruthy();
  expect(screen.getByText("Причина: style_load_failed")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Карта 3D" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByText("3D доступен при загрузке онлайн-карты")).toBeTruthy();
  expect(screen.getByRole("button", { name: "office-east" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "east-1" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "eng-east-01, участок 1" })).toBeTruthy();
  expect(screen.getByText("Модельная оценка, не текущие пробки")).toBeTruthy();
  expect(screen.getByText("Линия показывает последовательность визитов; не навигация по улицам.")).toBeTruthy();
  expect(screen.getByText("© OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors")).toBeTruthy();
  expect(mock.remove).toHaveBeenCalledOnce();
  expect(fetch).not.toHaveBeenCalled();
});
it("moves loading to online when a recoverable early error is followed by map.load", async () => {
  mock.autoLoad = false;
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await act(async () => { await Promise.resolve(); });
  act(() => mock.handlers.get("error")?.());
  expect(screen.getByText("Подложка: loading")).toBeTruthy();
  act(() => mock.handlers.get("load")?.());
  expect(await screen.findByText("OpenFreeMap")).toBeTruthy();
  expect(screen.getByText("Подложка: online")).toBeTruthy();
  expect(screen.queryByText("Офлайн-схема")).toBeNull();
});
it("classifies a zero-size container without constructing MapLibre", async () => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 0 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 0 });
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  expect(await screen.findByText("Офлайн-схема")).toBeTruthy();
  expect(screen.getByText("Причина: container_unavailable")).toBeTruthy();
  expect(mock.constructor).not.toHaveBeenCalled();
});
it("keeps an initialized map on a non-critical resource error", async () => {
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await screen.findByText("OpenFreeMap");
  act(() => mock.handlers.get("error")?.());
  expect(screen.queryByText("Офлайн-схема")).toBeNull();
  expect(mock.remove).not.toHaveBeenCalled();
});
it("recomputes bounds after plan coordinates/profile change and handles empty geometry", async () => {
  const { rerender } = render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await screen.findByText("OpenFreeMap");
  expect(mock.fitBounds).toHaveBeenCalledOnce();
  rerender(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" trafficProfile="peak" />);
  await waitFor(() => expect(mock.fitBounds).toHaveBeenCalledTimes(2));
  rerender(<DispatcherMap data={undefined} filter="all" loading={false} />);
  expect(screen.getByText("Нет координат для отображения")).toBeTruthy();
});

it("click focuses a leg, dims other legs, and a second click restores route without refitting", async () => {
  const select = vi.fn();
  const data = { ...dashboard, territories: [{ territory: "east" as const, office_id: "office-east", office_coordinates: dashboard.requests[1].coordinates }] };
  render(<DispatcherMap data={data} filter="all" loading={false} selectedRoute="eng-east-01" onSelect={select} />);
  await screen.findByText("OpenFreeMap");
  const click = mock.layerHandlers.get("click:routeflow-lines")!;
  const event = { features: [{ properties: { id: "eng-east-01:1", engineer: "eng-east-01" } }] };
  act(() => click(event));
  expect(screen.getByRole("button", { name: "Снять выделение" })).toBeTruthy();
  expect(mock.setPaintProperty).toHaveBeenCalledWith("routeflow-lines", "line-opacity", .16);
  expect(mock.fitBounds).toHaveBeenCalledOnce();
  expect(select).not.toHaveBeenCalled();
  act(() => click(event));
  expect(screen.queryByRole("button", { name: "Снять выделение" })).toBeNull();
});

it("allows keyboard leg choice at overlaps and clears focus on profile change", async () => {
  const data = { ...dashboard, territories: [{ territory: "east" as const, office_id: "office-east", office_coordinates: dashboard.requests[1].coordinates }] };
  const { rerender } = render(<DispatcherMap data={data} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await screen.findByText("OpenFreeMap");
  fireEvent.change(screen.getByRole("combobox", { name: "Выбрать участок маршрута" }), { target: { value: "eng-east-01:1" } });
  expect(screen.getByRole("button", { name: "Снять выделение" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Карта 3D" }));
  expect(screen.getByRole("button", { name: "Снять выделение" })).toBeTruthy();
  rerender(<DispatcherMap data={data} filter="all" loading={false} selectedRoute="eng-east-01" trafficProfile="peak" />);
  expect(screen.queryByRole("button", { name: "Снять выделение" })).toBeNull();
  expect(fetch).not.toHaveBeenCalled();
});

it("highlights exact cached road geometry and animates arrows with timer cleanup", async () => {
  vi.useFakeTimers(); mock.autoLoad = false;
  const geometry: [number, number][] = [[37.7, 55.8], [37.65, 55.8], [37.6, 55.7]];
  const data = { ...dashboard, territories: [{ territory: "east" as const, office_id: "office-east", office_coordinates: dashboard.requests[1].coordinates }], plan: { ...dashboard.plan, routes: dashboard.plan.routes.map(route => ({ ...route, stops: route.stops.map(stop => ({ ...stop, routing_source: "road" as const, geometry })) })) } };
  const { unmount } = render(<DispatcherMap data={data} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await act(async () => { await Promise.resolve(); });
  act(() => mock.handlers.get("load")?.());
  fireEvent.change(screen.getByRole("combobox", { name: "Выбрать участок маршрута" }), { target: { value: "eng-east-01:1" } });
  expect(mock.setData).toHaveBeenCalledWith(expect.objectContaining({ features: [expect.objectContaining({ geometry: { type: "LineString", coordinates: geometry }, properties: expect.objectContaining({ color: expect.any(String) }) })] }));
  const count = mock.setData.mock.calls.length;
  act(() => vi.advanceTimersByTime(300));
  expect(mock.setData.mock.calls.length).toBeGreaterThan(count);
  unmount();
  const stopped = mock.setData.mock.calls.length;
  act(() => vi.advanceTimersByTime(500));
  expect(mock.setData.mock.calls.length).toBe(stopped);
});

it("respects reduced motion with static arrows instead of a running animation", async () => {
  vi.useFakeTimers(); mock.autoLoad = false;
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  render(<DispatcherMap data={dashboard} filter="all" loading={false} selectedRoute="eng-east-01" />);
  await act(async () => { await Promise.resolve(); });
  act(() => mock.handlers.get("load")?.());
  const count = mock.setData.mock.calls.length;
  act(() => vi.advanceTimersByTime(500));
  expect(mock.setData.mock.calls.length).toBe(count);
});
