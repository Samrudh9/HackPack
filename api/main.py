"""HackPack FastAPI application.

Run locally with::

    uvicorn api.main:app --reload

Design notes for v0.1
---------------------
* Request/response handling is synchronous and straightforward: no background
  jobs, queues, databases, or auth. Blocking work (GitHub, model inference)
  runs in FastAPI's threadpool via plain ``def`` handlers.
* CORS uses a configurable list of *exact* origins. Wildcards are rejected at
  configuration time; wildcard-subdomain matching is not supported in v0.1.
* A basic Content-Length guard enforces ``MAX_REQUEST_BODY_BYTES``. This is
  validation, not abuse protection: an internet-facing deployment needs rate
  limiting and a reverse proxy in front (see README).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import analyze, generate, pitch
from api.schemas import HealthResponse
from config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Open-source hackathon deliverables generator. Analyzes a public GitHub "
            "repository and produces an editable six-slide deck, timed script, demo "
            "checklist, and ZIP bundle — with honest evidence classifications."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        # Exact origins only; wildcard entries are rejected by Settings validation.
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def request_size_guard(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body exceeds the {settings.MAX_REQUEST_BODY_BYTES}-byte limit."},
            )
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak stack traces, tokens, or repository text to clients.
        return JSONResponse(status_code=500, content={"detail": f"Internal server error ({type(exc).__name__})."})

    @app.get("/api/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            app=settings.APP_NAME,
            version=settings.APP_VERSION,
            llm_model=settings.LLM_MODEL,
            llm_fallback_enabled=settings.LLM_FALLBACK_ENABLED,
            default_pitch_duration_minutes=settings.DEFAULT_PITCH_DURATION_MINUTES,
        )

    app.include_router(analyze.router, prefix="/api")
    app.include_router(pitch.router, prefix="/api")
    app.include_router(generate.router, prefix="/api")
    return app


app = create_app()
