from pydantic import BaseModel, Field


class DependencyHealth(BaseModel):
    name: str
    status: str
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    dependencies: list[DependencyHealth] = Field(default_factory=list)
