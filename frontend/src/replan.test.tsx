import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { dashboard } from "./test/fixtures";

const api = vi.hoisted(() => ({ fetchDashboard: vi.fn(), applyReplan: vi.fn(), buildRoadGeometry: vi.fn() }));
const { fetchDashboard, applyReplan, buildRoadGeometry } = api;
vi.mock("./api/client", () => api);
vi.mock("./components/DispatcherMap", () => ({ DispatcherMap: ({ data, selectedRoute }: { data?: typeof dashboard; selectedRoute?: string }) => <div data-testid="map" data-selected={selectedRoute}>{data?.plan.routes.map((route) => route.engineer_id).join(",")}</div> }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });
beforeEach(() => {
  buildRoadGeometry.mockResolvedValue({ engineer_id: "eng-east-01", provider_request_count: 1, preserves_plan: true, legs: [{ request_id: "east-1", sequence: 1, geometry: [[37.5, 55.7], [37.6, 55.8]], source: "on_demand" }] });
});

function setup() {
  fetchDashboard.mockResolvedValue(dashboard);
  applyReplan.mockResolvedValue({ replanned_plan: { ...dashboard.plan, routes: [...dashboard.plan.routes, { ...dashboard.plan.routes[0], engineer_id: "reserve-east-emergency-01" }] }, diff: { emergency_reserve_activated: true, activated_reserve_engineer_id: "reserve-east-emergency-01", committed_visit_count: 29 } });
  render(<App />);
}

describe("REPLAN-001 simulation", () => {
  it("discards canonical road geometry arriving after replan", async () => {
    let failOld!: (reason: Error) => void;
    buildRoadGeometry.mockReturnValueOnce(new Promise((_resolve, reject) => { failOld = reject; }));
    setup();
    fireEvent.click(await screen.findByLabelText("Выбрать маршрут eng-east-01"));
    await waitFor(() => expect(buildRoadGeometry).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Срочная авария · 14:30" }));
    await screen.findByText("Аварийный резерв активирован");
    await act(async () => failOld(new Error("OLD CANONICAL FAILURE")));
    fireEvent.click(screen.getByLabelText("Закрыть детали маршрута"));
    fireEvent.click(screen.getByLabelText("Выбрать маршрут eng-east-01"));
    await waitFor(() => expect(buildRoadGeometry).toHaveBeenCalledWith("optimized", "eng-east-01", "east", "standard", "event-east-urgent-1430"));
    expect(screen.queryByText("OLD CANONICAL FAILURE")).toBeNull();
  });
  it("unassigned entry exists only in the right panel and preserves the selected map route", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01"));
    expect(screen.queryByRole("button", { name: /Неназначенные заявки/ })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Неназначенные" }));
    expect(screen.getByRole("tab", { name: "Неназначенные" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Нельзя вставить в фиксированный финальный план.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Карта маршрутов" }));
    expect(screen.getByRole("tab", { name: "Неназначенные" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01");
    expect(fetchDashboard).toHaveBeenCalledTimes(1);
  });
  it("comparison opens actual API metrics and closes with Escape without reloading the plan", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01"));
    fireEvent.click(screen.getByRole("button", { name: "Сравнение планов" }));
    expect(screen.getByText("+65 к baseline")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("dialog", { name: "Сравнение планов" }), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetchDashboard).toHaveBeenCalledTimes(1);
  });
  it("collapses and restores plan controls without changing active route", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01"));
    fireEvent.click(screen.getByRole("button", { name: "Свернуть управление планом" }));
    expect(screen.getByRole("button", { name: "Развернуть управление планом" }).getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01");
    fireEvent.click(screen.getByRole("button", { name: "Развернуть управление планом" }));
    expect(screen.getByRole("button", { name: "Свернуть управление планом" }).getAttribute("aria-expanded")).toBe("true");
  });
  it("selects the first active route after loading without opening a drawer", async () => {
    setup();
    await waitFor(() => expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01"));
    expect(screen.queryByLabelText("Закрыть детали маршрута")).toBeNull();
  });
  it("route selection updates map selection and opens the overlay timeline", async () => {
    const second = { ...dashboard.plan.routes[0], engineer_id: "eng-east-02" };
    fetchDashboard.mockResolvedValue({ ...dashboard, plan: { ...dashboard.plan, routes: [...dashboard.plan.routes, second] } });
    render(<App />);
    fireEvent.click(await screen.findByLabelText("Выбрать маршрут eng-east-02"));
    expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-02");
    expect(screen.getByLabelText("Закрыть детали маршрута")).toBeTruthy();
    await waitFor(() => expect(buildRoadGeometry).toHaveBeenCalledWith("optimized", "eng-east-02", "east", "standard", undefined));
  });
  it("hydrates a selected route on open and shows controlled retry on failure", async () => {
    setup();
    buildRoadGeometry.mockRejectedValueOnce(new Error("routing unavailable"));
    fireEvent.click(await screen.findByLabelText("Выбрать маршрут eng-east-01"));
    expect(await screen.findByText("routing unavailable")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByText(/Дорожная геометрия готова/)).toBeTruthy();
    expect(buildRoadGeometry).toHaveBeenCalledTimes(2);
  });
  it("posts the selected East urgent event with traffic profile", async () => {
    setup(); fireEvent.click(await screen.findByText("Восток")); fireEvent.click(screen.getByText("Срочная авария · 14:30"));
    await waitFor(() => expect(applyReplan).toHaveBeenCalledWith("event-east-urgent-1430", "standard"));
  });
  it("shows reserve diff and reserve route after success", async () => {
    setup(); fireEvent.click(await screen.findByText("Восток")); fireEvent.click(screen.getByText("Срочная авария · 14:30"));
    expect(await screen.findByText(/Аварийный резерв активирован/)).toBeTruthy();
    expect(screen.getByTestId("map").textContent).toContain("reserve-east-emergency-01");
    expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("reserve-east-emergency-01");
  });
  it("reset removes reserve and reloads canonical plan", async () => {
    setup(); fireEvent.click(await screen.findByText("Восток")); fireEvent.click(screen.getByText("Срочная авария · 14:30")); await screen.findByText(/Аварийный резерв активирован/);
    fireEvent.click(screen.getByText("Сбросить сценарий"));
    await waitFor(() => expect(fetchDashboard).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/Аварийный резерв активирован/)).toBeNull();
    await waitFor(() => expect(screen.getByTestId("map").getAttribute("data-selected")).toBe("eng-east-01"));
    expect(screen.getByTestId("map").textContent).not.toContain("reserve-east-emergency-01");
  });
  it("keeps a retryable error state when replan API fails", async () => {
    setup(); applyReplan.mockRejectedValueOnce(new Error("replan failed")); fireEvent.click(await screen.findByText("Восток")); fireEvent.click(screen.getByText("Срочная авария · 14:30"));
    expect(await screen.findByText("replan failed")).toBeTruthy();
    fireEvent.click(screen.getByText("Повторить"));
    expect(fetchDashboard).toHaveBeenCalled();
  });
});
