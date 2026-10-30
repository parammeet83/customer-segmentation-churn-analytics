"""FastAPI application factory: read-only CustomerPulse API."""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from customerpulse import __version__
from customerpulse.api.routes import router
from customerpulse.settings import get_settings

logger = logging.getLogger("customerpulse.api")


def _log(event: dict) -> None:
    logger.info(json.dumps(event, default=str))


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    app = FastAPI(
        title="CustomerPulse API",
        version=__version__,
        description=(
            "Read-only API for CustomerPulse: RFM segmentation, behavioural churn risk, SHAP "
            "explanations and retention scenarios built from the UCI Online Retail II dataset "
            "(CC BY 4.0, doi:10.24432/C5CG6D). Monetary scenario values are estimates under stated "
            "assumptions, not observed savings."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
        allow_credentials=False,
        max_age=600,
    )

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if (
            request.method == "GET"
            and response.status_code == 200
            and request.url.path.startswith("/api/v1/")
            and not request.url.path.endswith("/health")
        ):
            response.headers["Cache-Control"] = "public, max-age=300"
        _log(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        return response

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request: Request, exc: SQLAlchemyError):
        _log({"event": "db_error", "path": request.url.path, "error": type(exc).__name__})
        return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        _log({"event": "unhandled_error", "path": request.url.path, "error": type(exc).__name__})
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"name": "CustomerPulse API", "docs": "/api/docs", "health": "/api/v1/health"}

    return app


app = create_app()
