# Архитектура RouteFlow

## Дорожный кэш и routing modes

`road_matrix_cache.json` хранит только immutable pair distance/base duration и индексируется один раз на процесс по path+mtime. `road_geometry_cache.json` хранит GeoJSON лишь для выбранных legs и открывается лениво при явном запросе geometry. Snapshot repositories держат общую ссылку на индекс, а не Pydantic-копии cache.

`fallback_only` — default offline planner; `road_if_available` — cache/self-hosted OSRM/fallback; `road_required` — cache/self-hosted OSRM или controlled `routing_unavailable`. Отдельный interactive geometry endpoint не пересчитывает план: при открытии одного route он получает GeoJSON для фиксированной последовательности визитов одним запросом, memoizes результат и накладывает его только на UI. Windows launcher использует public demo OSRM лишь для этого явного действия; production должен направлять `ROUTEFLOW_ROUTE_GEOMETRY_URL` на self-hosted OSRM Москвы/МО.

```mermaid
flowchart LR
  A[CSV/XLSX] --> B[loader / normalization]
  B --> C[enrichment / normatives / geo]
  C --> D[baseline + VRPTW optimizer]
  D --> E[FastAPI]
  E --> F[React dispatcher]
```

Baseline идёт в source order и назначает первого feasible инженера. Optimized использует OR-Tools VRPTW с hard constraints территории, навыка, транспорта, смены, окна, service и travel. Цели: максимум coverage, затем минимум активных инженеров, затем минимум километров.

`standard`, `moderate`, `peak` — офлайн-множители actual travel time. Replan stateless: committed prefix неизменяем, mutable suffix пересчитывается. East urgent 14:30 использует incident-only emergency standby reserve, не regular engineer. Explanations детерминированы по plan evidence и diagnostics; LLM нет.
## Authentication boundary

An application-level middleware protects product routes under `/api/v1` when auth is enabled. The local demo identity source is an environment-configured dispatcher; successful login produces a short-lived HMAC-signed `HttpOnly` cookie. Snapshot repositories, planners and domain models do not depend on identity and are unchanged. This keeps the identity source replaceable by corporate SSO without coupling it to optimization logic.

