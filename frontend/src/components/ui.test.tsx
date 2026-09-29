import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ControlBar } from "./ControlBar";
import { KpiStrip } from "./KpiStrip";
import { RoutePanel } from "./RoutePanel";
import { SidePanel } from "./SidePanel";
import { dashboard } from "../test/fixtures";

const dialogMethods = ["showModal", "close"] as const;
const dialogDescriptors = dialogMethods.map(name => Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name));
afterEach(() => {
  cleanup(); vi.restoreAllMocks();
  dialogMethods.forEach((name, index) => {
    const descriptor = dialogDescriptors[index];
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  });
});

describe("UI-002 real API projections", () => {
  it("expands unassigned details in one modal and restores focus and tab on Escape", () => {
    // jsdom lacks native dialog methods; model only their open/close DOM contract.
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
    Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
    const select = vi.fn();
    render(<RoutePanel data={dashboard} selectedRoute="eng-east-01" onSelect={select} />);
    fireEvent.click(screen.getByRole("tab", { name: "Неназначенные" }));
    const opener = screen.getByRole("button", { name: "Открыть подробнее ↗" });
    opener.focus(); fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Неназначенные заявки" });
    expect(within(dialog).getByText("Адрес отказа")).toBeTruthy();
    expect(within(dialog).getByText("10:00–12:00")).toBeTruthy();
    expect(within(dialog).getByText("60 мин")).toBeTruthy();
    expect(screen.getAllByText("Нельзя вставить в фиксированный финальный план.")).toHaveLength(1);
    // Native Escape dispatches cancel; jsdom does not implement browser key defaults.
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
    expect(screen.getByRole("tab", { name: "Неназначенные" }).getAttribute("aria-selected")).toBe("true");
    expect(select).not.toHaveBeenCalled();
  });
  it("renders baseline/optimized KPI values and a neutral distance comparison", () => {
    render(<KpiStrip data={dashboard} />);
    expect(screen.getByText("157")).toBeTruthy();
    expect(screen.getByText("+65 к baseline")).toBeTruthy();
    expect(screen.getByText(/Оптимизация сначала максимизирует покрытие/)).toBeTruthy();
    expect(screen.queryByText(/ухудш/i)).toBeNull();
  });
  it("switches between optimized and baseline plan kind", () => {
    const setPlan = vi.fn();
    render(<ControlBar territory="all" trafficProfile="standard" planKind="optimized" loading={false} error={false} onTerritory={vi.fn()} onTraffic={vi.fn()} onPlanKind={setPlan} />);
    fireEvent.click(screen.getByText("Baseline"));
    expect(setPlan).toHaveBeenCalledWith("baseline");
  });
  it("selects a route and exposes its timeline", () => {
    const select = vi.fn();
    render(<RoutePanel data={dashboard} onSelect={select} />);
    fireEvent.click(screen.getByText("eng-east-01"));
    expect(select).toHaveBeenCalledWith("eng-east-01");
    render(<RoutePanel data={dashboard} selectedRoute="eng-east-01" onSelect={select} />);
    expect(screen.getByText("east-1")).toBeTruthy();
  });
  it("groups all-mode routes by territory", () => {
    const all = { ...dashboard, territories: [{ territory: "east" as const, office_id: "office-east", office_coordinates: dashboard.requests[0].coordinates }] };
    render(<RoutePanel territory="all" data={all} onSelect={vi.fn()} />);
    expect(screen.getByText("Восток")).toBeTruthy();
  });
  it("collapses and expands the route workspace without losing its selected tab", () => {
    render(<RoutePanel data={dashboard} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole("tab", { name: "Неназначенные" }));
    const collapse = screen.getByRole("button", { name: "Свернуть панель маршрутов" });
    fireEvent.click(collapse);
    expect(screen.getByRole("button", { name: "Развернуть панель маршрутов" }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Развернуть панель маршрутов" }));
    expect(screen.getByRole("tab", { name: "Неназначенные" }).getAttribute("aria-selected")).toBe("true");
  });
  it("shows unassigned diagnostic text without feasible-insertion code", () => {
    render(<RoutePanel data={dashboard} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByText("Неназначенные"));
    expect(screen.getByText("Нельзя вставить в фиксированный финальный план.")).toBeTruthy();
    expect(screen.queryByText("final_plan_insertion_feasible")).toBeNull();
  });
  it("renders loading and retryable API error states", () => {
    const retry = vi.fn();
    const { rerender } = render(<SidePanel filter="all" onFilter={vi.fn()} loading data={undefined} onRetry={retry} />);
    expect(screen.getByText("Загружаем актуальный план…")).toBeTruthy();
    rerender(<SidePanel filter="all" onFilter={vi.fn()} loading={false} error="Нет соединения" data={undefined} onRetry={retry} />);
    fireEvent.click(screen.getByText("Повторить"));
    expect(retry).toHaveBeenCalledOnce();
  });
});
