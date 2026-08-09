import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import DEFAULT_JWT_SECRET_KEY, get_settings
from app.core.middleware import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.db import session as db_session
from app.schemas.auth import RegisterRequest
from app.services.code_repository_loader import (
    CodeRepositoryLoaderError,
    GitRepositoryLoader,
)
from app.services.health_service import HealthService


BASELINE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0001_baseline_current_schema.py"
)


def test_init_db_skips_create_all_when_auto_create_is_disabled(monkeypatch) -> None:
    called = False

    def fake_create_all(bind):
        nonlocal called
        called = True

    monkeypatch.setenv("DATABASE_AUTO_CREATE", "false")
    monkeypatch.setattr(db_session.Base.metadata, "create_all", fake_create_all)

    db_session.init_db()

    assert called is False


def test_production_config_rejects_dev_secret(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_AUTO_CREATE", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", DEFAULT_JWT_SECRET_KEY)
    monkeypatch.setenv("CODE_REPOSITORY_ALLOWED_HOSTS", "github.com")

    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        get_settings()


def test_production_config_requires_code_repository_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_AUTO_CREATE", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
    monkeypatch.delenv("CODE_REPOSITORY_ALLOWED_HOSTS", raising=False)

    with pytest.raises(ValueError, match="CODE_REPOSITORY_ALLOWED_HOSTS"):
        get_settings()


def test_register_request_enforces_password_policy() -> None:
    with pytest.raises(ValueError, match="Password"):
        RegisterRequest(email="user@example.com", password="weakpassword")

    request = RegisterRequest(
        email="user@example.com",
        password="correct-password",
    )

    assert request.email == "user@example.com"


def test_request_size_limit_middleware_rejects_large_body() -> None:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=4)

    @app.post("/upload")
    def upload():
        return {"ok": True}

    response = TestClient(app).post("/upload", content=b"too-large")

    assert response.status_code == 413


def test_security_headers_middleware_adds_headers() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/demo")
    def demo():
        return {"ok": True}

    response = TestClient(app).get("/demo")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_rate_limit_middleware_limits_by_client_and_path() -> None:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_window=1,
        window_seconds=60,
    )

    @app.get("/api/demo")
    def demo():
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/api/demo").status_code == 200
    assert client.get("/api/demo").status_code == 429


def test_health_service_reports_dependency_status(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(
        "app.services.health_service._read_url",
        lambda url: b"ok",
    )
    service = HealthService(
        database_engine_factory=lambda: engine,
        qdrant_url="http://qdrant",
        ollama_base_url="http://ollama",
    )

    response = service.check_dependencies()

    assert response.status == "ok"
    assert {dependency.name for dependency in response.dependencies} == {
        "postgres",
        "qdrant",
        "ollama",
    }


def test_code_repository_loader_rejects_unapproved_hosts() -> None:
    loader = GitRepositoryLoader(
        repositories_dir="/tmp/repositories",
        allowed_hosts=["github.com"],
    )

    with pytest.raises(CodeRepositoryLoaderError, match="not allowed"):
        loader.clone_repository(
            repo_url="https://example.invalid/company/repo.git",
            branch="main",
        )


def test_alembic_baseline_revision_is_declared() -> None:
    spec = importlib.util.spec_from_file_location(
        "baseline_current_schema",
        BASELINE_MIGRATION_PATH,
    )
    assert spec is not None
    baseline = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(baseline)

    assert baseline.revision == "0001_baseline_current_schema"
    assert baseline.down_revision is None
