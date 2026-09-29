# RouteFlow read-only API

## Road-routing availability

The default planner mode is `fallback_only`. If a configured routing service cannot return a requested road shape, the API returns controlled `503 routing_unavailable`; no provider URL or internal error is exposed.

Launch on Windows:

```powershell
.\scripts\start-api.ps1
```

Open `http://127.0.0.1:8000/docs`. The API is offline and reads only the allowlisted synthetic CSV files and local generated geocache.

GET endpoints: `/health`, `/api/v1/territories`, `/summary`, `/requests`, `/requests/{request_id}`, `/engineers`, `/engineers/{engineer_id}`, `/plans/{plan_kind}`, `/events`, `/events/{event_id}`. `POST /api/v1/replan` accepts `{ "event_id": "...", "traffic_profile": "standard|moderate|peak" }`; territory, effective time and payload are always read from the local event catalogue.

`/territories` includes each office's coordinate-quality DTO (`office_coordinates`) so the offline UI can draw office markers without inventing points.

Plans accept `territory=all|east|southeast|southcenter` and `traffic_profile=standard|moderate|peak`. Requests support `assignment_status`, `limit` (1..205) and `offset`. A replan response contains the immutable base plan, replanned plan, committed stops, event outcome and factual diff. Unknown events return 404.

Plan stop DTOs include the existing calculated inbound-leg fields: `waiting_minutes`, `travel_minutes` and `distance_km`; they do not add a return-to-office leg.

For an eligible urgent East incident, `diff.emergency_reserve_activated=true` and `diff.activated_reserve_engineer_id="reserve-east-emergency-01"` distinguish the incident-only standby resource from reassignment of a regular engineer.

`GET /api/v1/requests/{request_id}/explanation` projects verified plan evidence only. It accepts `plan_kind`, `traffic_profile` and optional `event_id`; an event is resolved statelessly. The response contains Russian summary/facts and an evidence scope, never OR-Tools internals or LLM text.

`POST /api/v1/plans/{plan_kind}/routes/{engineer_id}/road-geometry` hydrates only the selected published route. It accepts the same `territory` and `traffic_profile` context plus optional `event_id`. Existing cache shapes are returned without network; otherwise one OSRM request contains the complete ordered point sequence and returns one GeoJSON geometry per leg. The operation never changes assignments, stop order, schedule, metrics or canonical snapshots. Results are memoized in process. `503` leaves the dashed approximation visible.
## Authentication

Product endpoints under `/api/v1` are protected when `ROUTEFLOW_AUTH_ENABLED=true`. The Windows launcher enables this mode and exposes a single local dispatcher account configured by environment variables. Authentication is backend-owned; the frontend never embeds the password.

- `POST /api/v1/auth/login` validates credentials and sets a signed `HttpOnly`, `SameSite=Lax` session cookie.
- `GET /api/v1/auth/me` restores the current dispatcher session.
- `POST /api/v1/auth/logout` clears the cookie.
- `/health`, `/docs` and `/openapi.json` remain public for local diagnostics.

The current implementation is deliberately scoped to a local hackathon demo: one environment-configured dispatcher, no registration, password recovery, database, MFA or SSO. A production deployment must use HTTPS, a stable protected secret, `Secure` cookies and an organizational identity provider.

