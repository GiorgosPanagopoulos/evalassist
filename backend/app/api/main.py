"""FastAPI app factory: routers + exception mapping + CORS.

Οι domain exceptions του core/exceptions.py γίνονται map σε HTTP status
codes εδώ — μόνο εδώ, ποτέ πιο κάτω στο retrieval layer."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_meta, routes_query
from app.core.config import get_settings
from app.core.exceptions import IsolationError, LLMUnavailableError, NotFoundError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="EvalAssist API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_query.router, prefix="/query", tags=["query"])
    app.include_router(routes_meta.router, tags=["meta"])

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(IsolationError)
    async def _isolation_handler(request: Request, exc: IsolationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(LLMUnavailableError)
    async def _llm_unavailable_handler(request: Request, exc: LLMUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
