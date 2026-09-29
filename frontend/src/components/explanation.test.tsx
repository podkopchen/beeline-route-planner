import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoutePanel } from "./RoutePanel";
import { dashboard } from "../test/fixtures";

const api = vi.hoisted(() => ({ fetchExplanation: vi.fn() }));
vi.mock("../api/client", () => api);
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const assigned = { title: "Заявка назначена", summary: "Визит помещается в окно.", facts: [{ label_ru: "Инженер", value: "eng-east-01" }] };

describe("EXPL-001 request drawer", () => {
  it("ignores a delayed explanation for the previous request", async () => {
    let finishFirst!: (value: typeof assigned) => void;
    api.fetchExplanation.mockReturnValueOnce(new Promise(resolve => { finishFirst = resolve; }))
      .mockResolvedValueOnce({ ...assigned, summary: "Объяснение второй заявки" });
    render(<RoutePanel data={dashboard} selectedRoute="eng-east-01" onSelect={vi.fn()} planKind="baseline" trafficProfile="peak" />);
    fireEvent.click(screen.getByText("east-1"));
    expect(api.fetchExplanation).toHaveBeenCalledWith("east-1", undefined, "baseline", "peak");
    fireEvent.click(screen.getByText("Неназначенные"));
    fireEvent.click(screen.getByText("east-2"));
    await screen.findByText("Объяснение второй заявки");
    await act(async () => finishFirst(assigned));
    expect(screen.queryByText(assigned.summary)).toBeNull();
    expect(screen.getByText("Объяснение второй заявки")).toBeTruthy();
  });
  it("loads assigned explanation only after selecting a request", async () => { api.fetchExplanation.mockResolvedValue(assigned); render(<RoutePanel data={dashboard} selectedRoute="eng-east-01" onSelect={vi.fn()} />); expect(api.fetchExplanation).not.toHaveBeenCalled(); fireEvent.click(screen.getByText("east-1")); expect(await screen.findByText("Визит помещается в окно.")).toBeTruthy(); fireEvent.click(screen.getByText("Факты")); expect(screen.getAllByText(/eng-east-01/).length).toBeGreaterThan(1); });
  it("renders unassigned diagnostic scope", async () => { api.fetchExplanation.mockResolvedValue({ ...assigned, summary: "Нельзя вставить", evidence_scope: "Только фиксированный план." }); render(<RoutePanel data={dashboard} onSelect={vi.fn()} />); fireEvent.click(screen.getByText("Неназначенные")); fireEvent.click(screen.getByText("east-2")); expect(await screen.findByText("Только фиксированный план.")).toBeTruthy(); });
  it("shows loading error and retries without changing selection", async () => { api.fetchExplanation.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(assigned); render(<RoutePanel data={dashboard} selectedRoute="eng-east-01" onSelect={vi.fn()} />); fireEvent.click(screen.getByText("east-1")); expect(await screen.findByText("offline")).toBeTruthy(); fireEvent.click(screen.getByText("Повторить")); expect(await screen.findByText("Визит помещается в окно.")).toBeTruthy(); });
  it("passes active replan event id for urgent explanation", async () => { api.fetchExplanation.mockResolvedValue({ ...assigned, facts: [{ label_ru: "Инженер", value: "reserve-east-emergency-01" }] }); render(<RoutePanel data={dashboard} selectedRoute="eng-east-01" onSelect={vi.fn()} eventId="event-east-urgent-1430" />); fireEvent.click(screen.getByText("east-1")); await screen.findByText("Визит помещается в окно."); expect(api.fetchExplanation).toHaveBeenCalledWith("east-1", "event-east-urgent-1430", "optimized", "standard"); });
});
