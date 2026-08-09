from pydantic import BaseModel, Field


DEFAULT_CODE_INCLUDE_GLOBS = [
    "**/*.py",
    "**/*.js",
    "**/*.jsx",
    "**/*.ts",
    "**/*.tsx",
    "**/*.java",
    "**/*.go",
    "**/*.rs",
    "**/*.c",
    "**/*.h",
    "**/*.cpp",
    "**/*.hpp",
]
DEFAULT_CODE_EXCLUDE_GLOBS = [
    "**/.git/**",
    "**/.venv/**",
    "**/venv/**",
    "**/node_modules/**",
    "**/dist/**",
    "**/build/**",
    "**/__pycache__/**",
]


class CodeIngestRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)
    branch: str = Field(default="main", min_length=1)
    include_globs: list[str] = Field(default_factory=lambda: DEFAULT_CODE_INCLUDE_GLOBS.copy())
    exclude_globs: list[str] = Field(default_factory=lambda: DEFAULT_CODE_EXCLUDE_GLOBS.copy())

    model_config = {"extra": "allow"}


class CodeIngestResponse(BaseModel):
    repository_id: int
    repo_name: str
    repo_url: str
    branch: str
    commit_sha: str
    storage_path: str
    status: str
    files: int = Field(..., ge=0)
    chunks: int = Field(..., ge=0)
    embeddings: int = Field(..., ge=0)
    collection_name: str
    stored_vectors: int = Field(..., ge=0)
    saved_chunks: int = Field(..., ge=0)
    vector_size: int | None

    model_config = {"extra": "allow"}
