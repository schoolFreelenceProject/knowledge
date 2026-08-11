from __future__ import annotations

import time
import urllib.request
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.schemas.health import DependencyHealth, HealthResponse


class HealthService:
    def __init__(
        self,
        database_engine_factory: Callable[[], Engine],
        qdrant_url: str,
        ollama_base_url: str | None = None,
        internal_generation_enabled: bool = False,
    ) -> None:
        self.database_engine_factory = database_engine_factory
        self.qdrant_url = qdrant_url.rstrip("/")
        self.ollama_base_url = (ollama_base_url or "").rstrip("/")
        self.internal_generation_enabled = internal_generation_enabled

    def check_dependencies(self) -> HealthResponse:
        dependencies = [
            self._check_postgres(),
            self._check_qdrant(),
        ]
        if self.internal_generation_enabled:
            dependencies.append(self._check_ollama())

        status = (
            "ok"
            if all(dependency.status == "ok" for dependency in dependencies)
            else "degraded"
        )
        return HealthResponse(status=status, dependencies=dependencies)

    def _check_postgres(self) -> DependencyHealth:
        started_at = time.perf_counter()
        try:
            with self.database_engine_factory().connect() as connection:
                connection.execute(text("SELECT 1"))
            return _ok("postgres", started_at)
        except Exception as exc:
            return _error("postgres", started_at, exc)

    def _check_qdrant(self) -> DependencyHealth:
        started_at = time.perf_counter()
        try:
            _read_url(f"{self.qdrant_url}/readyz")
            return _ok("qdrant", started_at)
        except Exception as exc:
            return _error("qdrant", started_at, exc)

    def _check_ollama(self) -> DependencyHealth:
        started_at = time.perf_counter()
        try:
            _read_url(f"{self.ollama_base_url}/api/tags")
            return _ok("ollama", started_at)
        except Exception as exc:
            return _error("ollama", started_at, exc)


def _read_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read()


def _ok(name: str, started_at: float) -> DependencyHealth:
    return DependencyHealth(
        name=name,
        status="ok",
        latency_ms=_elapsed_ms(started_at),
    )


def _error(name: str, started_at: float, exc: Exception) -> DependencyHealth:
    return DependencyHealth(
        name=name,
        status="error",
        latency_ms=_elapsed_ms(started_at),
        detail=str(exc),
    )


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)
