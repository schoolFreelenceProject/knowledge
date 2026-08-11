from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.code_ingest import router as code_ingest_router
from app.api.code_repositories import router as code_repositories_router
from app.api.documents import router as documents_router
from app.api.feedback import router as feedback_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.knowledge_explorer import router as knowledge_explorer_router
from app.api.permissions import router as permissions_router
from app.api.traces import router as traces_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
settings = get_settings()
configure_logging(settings.log_level)


app = FastAPI(
    title="Company Knowledge Base API",
    description=(
        "Retrieval-first Company Knowledge Base API using FastAPI, Qdrant, "
        "PostgreSQL, and sentence-transformers."
    ),
    version="0.1.0",
)

app.add_middleware(
    RequestSizeLimitMiddleware,
    max_body_bytes=settings.max_request_body_bytes,
)
if settings.rate_limit_enabled:
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_window=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
if settings.security_headers_enabled:
    app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(code_ingest_router)
app.include_router(code_repositories_router)
app.include_router(documents_router)
app.include_router(ingest_router)
app.include_router(knowledge_explorer_router)
app.include_router(permissions_router)
app.include_router(traces_router)
app.include_router(feedback_router)
app.include_router(analytics_router)
app.include_router(users_router)
app.include_router(health_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
