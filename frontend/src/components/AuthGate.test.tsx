import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "./AuthGate";

const api = vi.hoisted(() => ({ fetchCurrentUser: vi.fn(), login: vi.fn(), logout: vi.fn() }));
vi.mock("../api/client", () => api);

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("dispatcher account flow", () => {
  it("shows animated startup state while session is checked", () => {
    api.fetchCurrentUser.mockReturnValue(new Promise(() => undefined));
    render(<AuthGate>{() => <div>workspace</div>}</AuthGate>);
    expect(screen.getByRole("status").textContent).toContain("Подготавливаем рабочее пространство");
    expect(screen.getByRole("img", { name: "Билайн" })).toBeTruthy();
  });

  it("renders login and authenticates without storing password in UI state", async () => {
    api.fetchCurrentUser.mockResolvedValue(null);
    api.login.mockResolvedValue({ username: "dispatcher", display_name: "Диспетчер смены", role: "dispatcher" });
    render(<AuthGate>{user => <div>workspace:{user.display_name}</div>}</AuthGate>);
    await screen.findByRole("heading", { name: "Вход в диспетчерскую" });
    fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "secret" } });
    fireEvent.submit(screen.getByRole("button", { name: /Войти в RouteFlow/ }).closest("form")!);
    expect(await screen.findByText("workspace:Диспетчер смены")).toBeTruthy();
    expect(api.login).toHaveBeenCalledWith("dispatcher", "secret");
  });

  it("shows invalid credentials and supports password visibility", async () => {
    api.fetchCurrentUser.mockResolvedValue(null);
    api.login.mockRejectedValue(new Error("Неверный логин или пароль."));
    render(<AuthGate>{() => <div>workspace</div>}</AuthGate>);
    const password = await screen.findByLabelText("Пароль") as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: "Показать пароль" }));
    expect(password.type).toBe("text");
    fireEvent.change(password, { target: { value: "wrong" } });
    fireEvent.submit(screen.getByRole("button", { name: /Войти в RouteFlow/ }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toContain("Неверный логин или пароль.");
  });

  it("restores an existing session and logs out", async () => {
    api.fetchCurrentUser.mockResolvedValue({ username: "dispatcher", display_name: "Диспетчер смены", role: "dispatcher" });
    api.logout.mockResolvedValue(undefined);
    render(<AuthGate>{(user, signOut) => <button onClick={() => void signOut()}>{user.display_name}</button>}</AuthGate>);
    fireEvent.click(await screen.findByRole("button", { name: "Диспетчер смены" }));
    await waitFor(() => expect(api.logout).toHaveBeenCalledOnce());
    expect(await screen.findByRole("heading", { name: "Вход в диспетчерскую" })).toBeTruthy();
  });
});
