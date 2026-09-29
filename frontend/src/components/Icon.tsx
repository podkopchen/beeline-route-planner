type IconName = "route" | "map" | "chart" | "alert" | "layers" | "arrow";
const paths: Record<IconName, string> = {
  route: "M5 4a2 2 0 1 0 0 .01M19 20a2 2 0 1 0 0 .01M5 6v8a4 4 0 0 0 4 4h6M19 18v-8a4 4 0 0 0-4-4h-4",
  map: "m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2ZM9 3v16M15 5v16",
  chart: "M4 3v17h17M8 16v-5M13 16V7M18 16V4",
  alert: "m12 3 10 18H2ZM12 9v5M12 17v1",
  layers: "m12 3 10 6-10 6L2 9ZM2 13l10 6 10-6M2 17l10 6 10-6",
  arrow: "M4 12h16m-6-6 6 6-6 6",
};
export function Icon({ name }: { name: IconName }) {
  return <svg className="ui-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name]} /></svg>;
}
