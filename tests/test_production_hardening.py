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
from scripts.audit_vector_consistency import (
    PostgresVectorAudit,
    _build_report,
    _find_duplicate_references,
)


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


def test_default_config_does_not_require_ollama_settings(monkeypatch) -> None:
    monkeypatch.delenv("INTERNAL_GENERATION_ENABLED", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    monkeypatch.setenv("OLLAMA_MODEL", "")

    settings = get_settings()

    assert settings.internal_generation_enabled is False


def test_internal_generation_requires_ollama_settings(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_GENERATION_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")

    with pytest.raises(ValueError, match="OLLAMA_BASE_URL"):
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


def test_health_service_reports_required_dependency_status(monkeypatch) -> None:
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
    }


def test_health_service_checks_ollama_only_when_internal_generation_enabled(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    checked_urls: list[str] = []

    def fake_read_url(url: str) -> bytes:
        checked_urls.append(url)
        return b"ok"

    monkeypatch.setattr("app.services.health_service._read_url", fake_read_url)
    service = HealthService(
        database_engine_factory=lambda: engine,
        qdrant_url="http://qdrant",
        ollama_base_url="http://ollama",
        internal_generation_enabled=True,
    )

    response = service.check_dependencies()

    assert response.status == "ok"
    assert {dependency.name for dependency in response.dependencies} == {
        "postgres",
        "qdrant",
        "ollama",
    }
    assert "http://ollama/api/tags" in checked_urls


def test_default_compose_does_not_require_ollama() -> None:
    compose_text = (
        Path(__file__).resolve().parents[1] / "docker-compose.yml"
    ).read_text()

    assert "profiles:\n      - ollama" in compose_text
    assert "ollama:\n        condition: service_healthy" not in compose_text
    assert (
        "INTERNAL_GENERATION_ENABLED: ${INTERNAL_GENERATION_ENABLED:-false}"
        in compose_text
    )
    assert "alembic upgrade head" in compose_text
    assert "frontend:" in compose_text
    assert "kb_data:/app/data" in compose_text
    assert "http://localhost:8000/health/ready" in compose_text
    assert "http://127.0.0.1/ >/dev/null" in compose_text
    assert "api:\n        condition: service_healthy" in compose_text


def test_backend_docker_image_uses_python_with_native_wheel_coverage() -> None:
    dockerfile_text = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert dockerfile_text.startswith("FROM python:3.11-slim")


def test_release_bootstrap_scripts_are_explicit_and_non_destructive() -> None:
    project_root = Path(__file__).resolve().parents[1]

    start_script = (project_root / "start.sh").read_text()
    reset_script = (project_root / "reset.sh").read_text()
    release_verify_script = (project_root / "scripts" / "release_verify.sh").read_text()

    assert "MCP_SERVICE_TOKEN_SHA256" in start_script
    assert "KB_BOOTSTRAP_ADMIN_PASSWORD" in start_script
    assert "docker compose up -d --build" in start_script
    assert "--yes-delete-all-data" in reset_script
    assert "docker compose down -v" in reset_script
    assert "git diff --check" in release_verify_script
    assert "python - --fail-on-inconsistency < scripts/audit_vector_consistency.py" in (
        release_verify_script
    )


def test_release_documentation_describes_default_stack_and_mcp_clients() -> None:
    release_doc = (
        Path(__file__).resolve().parents[1] / "docs" / "release.md"
    ).read_text()

    assert "./start.sh" in release_doc
    assert "postgres" in release_doc
    assert "qdrant" in release_doc
    assert "frontend" in release_doc
    assert "Ollama is optional" in release_doc
    assert "Codex Setup" in release_doc
    assert "Claude Code Setup" in release_doc


def test_ollama_python_client_is_optional_requirement() -> None:
    project_root = Path(__file__).resolve().parents[1]

    assert "ollama" not in (project_root / "requirements.txt").read_text()
    assert "ollama" in (project_root / "requirements-ollama.txt").read_text()


def test_vector_consistency_report_marks_clean_state_consistent() -> None:
    postgres_audit = PostgresVectorAudit(
        document_point_ids=["doc-point"],
        code_point_ids=["code-point"],
        duplicate_references=[],
        invalid_references={
            "document_chunks_missing_document": [],
            "code_files_missing_repository": [],
            "code_chunks_missing_repository": [],
            "code_chunks_missing_file": [],
            "code_chunks_file_repository_mismatch": [],
        },
    )

    report = _build_report(
        collection_name="company_documents",
        postgres_audit=postgres_audit,
        qdrant_point_ids={"doc-point", "code-point"},
        initial_orphan_ids=[],
        deleted_orphan_ids=[],
    )

    assert report["consistent"] is True
    assert report["counts"]["orphan_qdrant_points"] == 0
    assert report["counts"]["missing_qdrant_points"] == 0
    assert report["counts"]["duplicate_point_references"] == 0


def test_vector_consistency_report_exposes_orphans_missing_and_duplicates() -> None:
    postgres_audit = PostgresVectorAudit(
        document_point_ids=["shared-point", "missing-point"],
        code_point_ids=["shared-point"],
        duplicate_references=[
            {
                "qdrant_point_id": "shared-point",
                "reference_count": 2,
                "document_chunk_ids": [1],
                "code_chunk_ids": [2],
            }
        ],
        invalid_references={
            "document_chunks_missing_document": [{"id": 1}],
            "code_files_missing_repository": [],
            "code_chunks_missing_repository": [],
            "code_chunks_missing_file": [],
            "code_chunks_file_repository_mismatch": [],
        },
    )

    report = _build_report(
        collection_name="company_documents",
        postgres_audit=postgres_audit,
        qdrant_point_ids={"shared-point", "orphan-point"},
        initial_orphan_ids=["orphan-point"],
        deleted_orphan_ids=[],
    )

    assert report["consistent"] is False
    assert report["counts"]["orphan_qdrant_points"] == 1
    assert report["counts"]["missing_qdrant_points"] == 1
    assert report["counts"]["duplicate_point_references"] == 1
    assert report["counts"]["invalid_references"][
        "document_chunks_missing_document"
    ] == 1


def test_vector_consistency_duplicate_detection_crosses_content_tables() -> None:
    duplicates = _find_duplicate_references(
        document_rows=[
            {"id": 1, "qdrant_point_id": "shared-point"},
        ],
        code_rows=[
            {"id": 2, "qdrant_point_id": "shared-point"},
        ],
    )

    assert duplicates == [
        {
            "qdrant_point_id": "shared-point",
            "document_chunk_ids": [1],
            "code_chunk_ids": [2],
            "reference_count": 2,
        }
    ]


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
