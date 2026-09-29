"""RouteFlow read-only FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.routes import router
from app.api.schemas import HealthDto
from app.core.api_config import api_config
from app.core.auth_config import auth_config
from app.repositories.snapshots import RouteFlowSnapshotRepository
from app.services.auth import COOKIE_NAME, read_session
from app.services.diagnostics import DiagnosticInvariantError
from app.services.routing import RoutingUnavailableError

PUBLIC_PATHS = {
    "/health",
    "/api/health",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/auth/logout",
}


def create_app(repository: RouteFlowSnapshotRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="RouteFlow API",
        version="1.0.0",
        description="Read-only offline RouteFlow API.",
    )
    app.state.repository = repository or RouteFlowSnapshotRepository()
    config = auth_config()

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        if (
            not config.enabled
            or request.url.path in PUBLIC_PATHS
            or not request.url.path.startswith("/api/v1/")
        ):
            return await call_next(request)
        user = read_session(request.cookies.get(COOKIE_NAME), config)
        if user is None:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "authentication_required", "message": "Требуется вход"}},
            )
        request.state.user = user
        return await call_next(request)

    # Outermost: preflight carries no cookie; even a 401 needs CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_config().cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(DiagnosticInvariantError)
    async def diagnostic_invariant_error(_: Request, __: DiagnosticInvariantError):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "plan_invariant_failed",
                    "message": "План не прошёл внутреннюю проверку согласованности.",
                }
            },
        )

    @app.exception_handler(RoutingUnavailableError)
    async def routing_unavailable(_: Request, __: RoutingUnavailableError):
        return JSONResponse(
            status_code=503,
            content={
                "code": "routing_unavailable",
                "message": "Дорожный сервис временно недоступен. Опубликованный план не изменён.",
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Некорректные параметры запроса.",
                }
            },
        )

    @app.get("/health", tags=["system"], response_model=HealthDto)
    def healthcheck() -> HealthDto:
        return HealthDto(status="ok", api_version=app.version, offline=True)

    @app.get("/api/health", include_in_schema=False)
    def legacy_healthcheck() -> dict[str, str]:
        return {"status": "ok", "stage": "infrastructure"}

    app.include_router(auth_router)
    app.include_router(router, tags=["read-only"])
    return app


app = create_app()
