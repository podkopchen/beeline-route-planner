import { useRef, useState } from "react";
import { trafficColors, type Scene } from "../map/scene";

// Pure SVG fallback: no map engine, tiles, images, fonts or network requests.
export function OfflineMap({ scene, onSelect }: { scene: Scene; onSelect?: (engineer: string) => void }) {
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const drag = useRef<{ x: number; y: number }>();
  const [detail, setDetail] = useState<string>();
  const project = ([lng, lat]: number[]) => [lng, -Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)) * 180 / Math.PI];
  const coords = [...scene.focusPositions, ...scene.legs.flatMap(leg => leg.positions)].map(project);
  const xs = coords.map(p => p[0]), ys = coords.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const scale = Math.min(710 / (maxX - minX || .02), 240 / (maxY - minY || .02));
  const xy = (point: number[]) => { const [x, y] = project(point); return [470 + (x - (minX + maxX) / 2) * scale, 400 + (y - (minY + maxY) / 2) * scale]; };
  return <div className="offline-canvas">
    <svg viewBox="0 0 1200 650" role="img" aria-label="Локальная схема заявок и маршрутов" onPointerDown={event => { drag.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerUp={() => { drag.current = undefined; }} onPointerMove={event => { if (!drag.current) return; const rect = event.currentTarget.getBoundingClientRect(); const dx = (event.clientX - drag.current.x) * 1200 / rect.width, dy = (event.clientY - drag.current.y) * 650 / rect.height; setView(v => ({ ...v, x: v.x + dx, y: v.y + dy })); drag.current = { x: event.clientX, y: event.clientY }; }}>
      <defs><pattern id="map-grid" width="60" height="60" patternUnits="userSpaceOnUse"><path d="M60 0H0V60" fill="none" stroke="#e0e5e5" strokeWidth="1" /></pattern></defs>
      <rect width="1200" height="650" fill="#f4f6f4" /><rect width="1200" height="650" fill="url(#map-grid)" />
      <g transform={`translate(${view.x} ${view.y}) translate(470 330) scale(${view.zoom}) translate(-470 -330)`}>
        {scene.legs.map(leg => { const points = leg.positions.map(p => xy(p).join(",")).join(" "); return <g key={leg.id} tabIndex={0} role="button" aria-label={`${leg.engineer}, участок ${leg.sequence}`} onClick={() => { setDetail(leg.detail); onSelect?.(leg.engineer); }} onKeyDown={e => { if (e.key === "Enter") { setDetail(leg.detail); onSelect?.(leg.engineer); } }}><title>{leg.detail}</title>{leg.selected && <polyline points={points} fill="none" stroke="white" strokeWidth="11" strokeOpacity=".9" vectorEffect="non-scaling-stroke" />}<polyline points={points} fill="none" stroke={leg.selected ? trafficColors[leg.level] : "#6d7c86"} strokeWidth={leg.selected ? 7 : 1.5} strokeOpacity={leg.selected ? 1 : .2} strokeLinecap="round" vectorEffect="non-scaling-stroke" /></g>; })}
        {scene.points.map(point => { const [x, y] = xy(point.displayPosition); return <g key={point.id} transform={`translate(${x} ${y})`} tabIndex={0} role="button" aria-label={point.id} onClick={() => { setDetail(point.detail); if (point.engineer) onSelect?.(point.engineer); }} onKeyDown={e => { if (e.key === "Enter") setDetail(point.detail); }}><title>{point.detail}</title><circle r={point.kind === "office" ? 13 : point.sequence ? 10 : point.kind === "unassigned" ? 6 : 3.5} fill={point.kind === "office" ? "#20252a" : point.kind === "unassigned" ? "#df665d" : point.territory === "southeast" ? "#4f82c0" : point.territory === "southcenter" ? "#8b65ae" : "#ffcf22"} stroke="white" strokeWidth={point.sequence || point.kind === "office" ? 2 : 1} /><text textAnchor="middle" dy="4" fontSize="10" fontWeight="700" fill={point.kind === "office" ? "#ffcf22" : "#20252a"}>{point.label}</text></g>; })}
      </g>
    </svg>
    <div className="map-zoom"><button aria-label="Приблизить схему" onClick={() => setView(v => ({ ...v, zoom: Math.min(8, v.zoom * 1.4) }))}>+</button><button aria-label="Отдалить схему" onClick={() => setView(v => ({ ...v, zoom: Math.max(.5, v.zoom / 1.4) }))}>−</button><button aria-label="Показать все точки" onClick={() => setView({ x: 0, y: 0, zoom: 1 })}>↺</button></div>
    {detail && <div className="map-detail" role="status"><button aria-label="Закрыть точку" onClick={() => setDetail(undefined)}>×</button>{detail}</div>}
  </div>;
}
