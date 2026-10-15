"""FastAPI app factory: routers + auth + exception mapping + static frontend.

Οι domain exceptions του core/exceptions.py γίνονται map σε HTTP status
codes εδώ — μόνο εδώ, ποτέ πιο κάτω στο retrieval layer.

Όλα τα API routes είναι κάτω από /api. Δημόσια είναι ΜΟΝΟ /api/health και
/api/auth/login. Κάθε router με δεδομένα παίρνει require_user στο
include_router, και το tests/test_auth_route_coverage.py σπάει αν ένα νέο
route μείνει χωρίς auth. Frontend και API είναι same-origin (Vite dev
proxy τοπικά, portal στην παραγωγή), άρα κανένα CORS."""

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    routes_admin,
    routes_auth,
    routes_health,
    routes_meta,
    routes_query,
    routes_timeline,
)
from app.auth.deps import require_admin, require_user
from app.core.config import BASE_DIR, get_settings
from app.core.exceptions import (
    InvalidPeriodError,
    IsolationError,
    LLMUnavailableError,
    NotFoundError,
)

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    settings = get_settings()
    docs = settings.ENABLE_DOCS
    app = FastAPI(
        title="EvalAssist API",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    authenticated = [Depends(require_user)]

    # Δημόσια: /api/health και /api/auth/login. Τα υπόλοιπα /api/auth/*
    # δηλώνουν το session dependency ανά route (επιτρέπουν must_change_pw).
    app.include_router(routes_health.router, prefix="/api", tags=["meta"])
    app.include_router(routes_auth.router, prefix="/api/auth", tags=["auth"])

    app.include_router(
        routes_admin.router,
        prefix="/api/admin",
        tags=["admin"],
        dependencies=[Depends(require_admin)],
    )
    app.include_router(
        routes_query.router, prefix="/api/query", tags=["query"], dependencies=authenticated
    )
    app.include_router(routes_meta.router, prefix="/api", tags=["meta"], dependencies=authenticated)
    app.include_router(
        routes_timeline.router, prefix="/api", tags=["timeline"], dependencies=authenticated
    )

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(IsolationError)
    async def _isolation_handler(request: Request, exc: IsolationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(InvalidPeriodError)
    async def _invalid_period_handler(request: Request, exc: InvalidPeriodError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(LLMUnavailableError)
    async def _llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # Το build του frontend σερβίρεται στο /, ΜΕΤΑ τα /api routes ώστε να μην
    # τα σκιάζει, και μόνο αν υπάρχει (στο dev το σερβίρει το Vite).
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()
