import { type FormEvent, type ReactNode, useEffect, useState } from "react";

import { fetchCurrentUser, login, logout } from "../api/client";
import type { AuthUser } from "../types/api";
import { BeeLogo } from "./BeeLogo";

export function AuthGate({ children }: { children: (user: AuthUser, signOut: () => Promise<void>) => ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>();
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    fetchCurrentUser().then(value => { if (active) setUser(value); }).catch((reason: unknown) => {
      if (active) { setError(reason instanceof Error ? reason.message : "Сервис авторизации недоступен."); setUser(null); }
    });
    const expired = () => setUser(null);
    window.addEventListener("routeflow:session-expired", expired);
    return () => { active = false; window.removeEventListener("routeflow:session-expired", expired); };
  }, []);

  if (user === undefined) return <div className="auth-splash" role="status"><BeeLogo size={76} animated /><strong>RouteFlow</strong><span>Подготавливаем рабочее пространство</span></div>;
  if (user) return <div className="session-workspace">
    {children(user, async () => { await logout(); setUser(null); })}
    <div className="session-reveal" aria-hidden="true"><div className="session-emblem"><BeeLogo size={96} /><span>RouteFlow</span><small>Ваша смена. Ваш маршрут.</small></div></div>
  </div>;
  return <LoginScreen error={error} submitting={submitting} onSubmit={async (username, password) => {
    setSubmitting(true); setError(undefined);
    try { setUser(await login(username, password)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось выполнить вход."); }
    finally { setSubmitting(false); }
  }} />;
}

function LoginScreen({ error, submitting, onSubmit }: { error?: string; submitting: boolean; onSubmit: (username: string, password: string) => Promise<void> }) {
  const [showPassword, setShowPassword] = useState(false);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void onSubmit(String(form.get("username") ?? ""), String(form.get("password") ?? ""));
  };
  return <main className="auth-shell">
    <section className="auth-visual" aria-label="RouteFlow">
      <div className="auth-brand"><BeeLogo size={58} animated /><div><strong>RouteFlow</strong><span>Билайн Бизнес</span></div></div>
      <div className="auth-message"><span className="auth-kicker">Управление выездами</span><h1>Смена под контролем.<br />Каждый маршрут — на карте.</h1><p>Единое пространство для диспетчера: инженеры, заявки, временные окна и сценарное перепланирование.</p></div>
      <svg className="auth-network" viewBox="0 0 700 360" aria-hidden="true">
        <path d="M-20 280C130 250 130 85 280 118S420 325 720 100" />
        <path d="M45 335C190 190 390 305 670 30" />
        <circle cx="280" cy="118" r="7" />
        {/* Exact point at t=0.7 on the first path's second cubic segment. */}
        <circle cx="521.01" cy="209.35" r="7" />
        <circle cx="670" cy="30" r="7" />
      </svg>
      <small>Демонстрационный контур · synthetic data</small>
    </section>
    <section className="auth-form-side">
      <form className="login-card" onSubmit={submit}>
        <div className="login-heading"><span>RouteFlow ID</span><h2>Вход в диспетчерскую</h2><p>Используйте аккаунт, выданный администратором проекта.</p></div>
        <label><span>Логин</span><input name="username" autoComplete="username" defaultValue="dispatcher" required autoFocus /></label>
        <label><span>Пароль</span><div className="password-field"><input name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required /><button type="button" aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"} onClick={() => setShowPassword(value => !value)}>{showPassword ? "Скрыть" : "Показать"}</button></div></label>
        {error && <div className="login-error" role="alert"><i />{error}</div>}
        <button className="login-submit" disabled={submitting}>{submitting ? <><BeeLogo size={22} animated />Проверяем доступ…</> : <>Войти в RouteFlow <span>→</span></>}</button>
        <div className="login-security"><span>●</span><p><strong>Защищённая локальная сессия</strong><small>Пароль не хранится в браузере</small></p></div>
      </form>
    </section>
  </main>;
}
