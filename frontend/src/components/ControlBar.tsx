import type { PlanKind, Territory, TrafficProfile } from "../types/api";
const territories: [Territory, string][] = [["all", "Все"], ["east", "Восток"], ["southeast", "Юго-восток"], ["southcenter", "Югоцентр"]];
export function ControlBar({ territory, trafficProfile, planKind, loading, error, onTerritory, onTraffic, onPlanKind }: { territory: Territory; trafficProfile: TrafficProfile; planKind: PlanKind; loading: boolean; error: boolean; onTerritory: (value: Territory) => void; onTraffic: (value: TrafficProfile) => void; onPlanKind: (value: PlanKind) => void }) {
  const status = error ? "Ошибка API" : loading ? "Обновление" : "Данные готовы";
  const profileNames = { standard: "Обычная", moderate: "Умеренная", peak: "Пиковая" };
  return <header className="topbar">
    <div className="control-section territory-control"><span className="control-label">Территория</span><nav className="segmented" aria-label="Территория">{territories.map(([value, label]) => <button aria-pressed={territory === value} className={territory === value ? "active" : ""} key={value} onClick={() => onTerritory(value)}>{label}</button>)}</nav></div>
    <div className="control-section"><span className="control-label">Расчёт</span><div className="plan-toggle" role="group" aria-label="Тип плана"><button aria-pressed={planKind === "optimized"} className={planKind === "optimized" ? "active" : ""} onClick={() => onPlanKind("optimized")}>Оптимизированный</button><button aria-pressed={planKind === "baseline"} className={planKind === "baseline" ? "active" : ""} onClick={() => onPlanKind("baseline")}>Baseline</button></div></div>
    <label className="control-section traffic-select"><span className="control-label">Загруженность</span><select aria-label="Сценарий загруженности" value={trafficProfile} onChange={(e) => onTraffic(e.target.value as TrafficProfile)}>{(["standard", "moderate", "peak"] as TrafficProfile[]).map(profile => <option key={profile} value={profile}>{profileNames[profile]}</option>)}</select></label>
    <span className={`api-status ${error ? "error" : loading ? "loading" : ""}`}><i />{status}</span>
  </header>;
}
