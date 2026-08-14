import os
from dataclasses import dataclass


DEFAULT_APP_ENV = "development"
PRODUCTION_ENV_NAMES = {"prod", "production"}
DEFAULT_DOCUMENT_CHUNK_SIZE = 1000
DEFAULT_DOCUMENT_CHUNK_OVERLAP = 150
DEFAULT_EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_QDRANT_COLLECTION_NAME = "company_documents"
DEFAULT_INTERNAL_GENERATION_ENABLED = False
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://rag:rag_password@localhost:5432/company_rag"
)
DEFAULT_JWT_SECRET_KEY = "dev-only-change-this-secret-change-me"
DEFAULT_JWT_ALGORITHM = "HS256"
DEFAULT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
DEFAULT_RETRIEVAL_MODE = "vector"
DEFAULT_HYBRID_FUSION_STRATEGY = "rrf"
DEFAULT_HYBRID_VECTOR_WEIGHT = 0.6
DEFAULT_HYBRID_BM25_WEIGHT = 0.4
DEFAULT_HYBRID_CANDIDATE_MULTIPLIER = 4
DEFAULT_BM25_K1 = 1.5
DEFAULT_BM25_B = 0.75
DEFAULT_RERANKER_ENABLED = False
DEFAULT_RERANKER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_RERANKER_CANDIDATE_SIZE = 20
DEFAULT_RERANKER_BATCH_SIZE = 16
DEFAULT_DATABASE_AUTO_CREATE = True
DEFAULT_MAX_REQUEST_BODY_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_UPLOAD_FILE_SIZE = 25 * 1024 * 1024
DEFAULT_MAX_BULK_UPLOAD_SIZE = 256 * 1024 * 1024
DEFAULT_MAX_BULK_FILE_COUNT = 100
DEFAULT_MAX_UPLOAD_BYTES = DEFAULT_MAX_UPLOAD_FILE_SIZE
DEFAULT_PDF_MIN_TEXT_CHARS = 20
DEFAULT_PDF_OCR_ENABLED = True
DEFAULT_PDF_OCR_LANGUAGES = "jpn+eng"
DEFAULT_PDF_OCR_DPI = 200
DEFAULT_PDF_OCR_TIMEOUT_SECONDS = 120
DEFAULT_PDF_OCR_MAX_PAGES = 100
DEFAULT_PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS = 30
DEFAULT_SECURITY_HEADERS_ENABLED = True
DEFAULT_RATE_LIMIT_ENABLED = True
DEFAULT_RATE_LIMIT_REQUESTS = 120
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_CODE_REPOSITORY_ALLOWED_HOSTS = ["*"]
DEFAULT_AUDIT_LOG_ENABLED = True
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MCP_HOST = "0.0.0.0"
DEFAULT_MCP_PORT = 8001
DEFAULT_MCP_PATH = "/mcp"
DEFAULT_MCP_PUBLIC_URL = "http://localhost:8001/mcp"
DEFAULT_MCP_SERVICE_TOKEN_SHA256 = ""
DEFAULT_MCP_SERVICE_ACCOUNT_EMAIL = ""


@dataclass(frozen=True)
class AppSettings:
    app_env: str = DEFAULT_APP_ENV
    document_chunk_size: int = DEFAULT_DOCUMENT_CHUNK_SIZE
    document_chunk_overlap: int = DEFAULT_DOCUMENT_CHUNK_OVERLAP
    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL_NAME
    qdrant_url: str = DEFAULT_QDRANT_URL
    qdrant_collection_name: str = DEFAULT_QDRANT_COLLECTION_NAME
    internal_generation_enabled: bool = DEFAULT_INTERNAL_GENERATION_ENABLED
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    database_url: str = DEFAULT_DATABASE_URL
    jwt_secret_key: str = DEFAULT_JWT_SECRET_KEY
    jwt_algorithm: str = DEFAULT_JWT_ALGORITHM
    jwt_access_token_expire_minutes: int = DEFAULT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    retrieval_mode: str = DEFAULT_RETRIEVAL_MODE
    hybrid_fusion_strategy: str = DEFAULT_HYBRID_FUSION_STRATEGY
    hybrid_vector_weight: float = DEFAULT_HYBRID_VECTOR_WEIGHT
    hybrid_bm25_weight: float = DEFAULT_HYBRID_BM25_WEIGHT
    hybrid_candidate_multiplier: int = DEFAULT_HYBRID_CANDIDATE_MULTIPLIER
    bm25_k1: float = DEFAULT_BM25_K1
    bm25_b: float = DEFAULT_BM25_B
    reranker_enabled: bool = DEFAULT_RERANKER_ENABLED
    reranker_model_name: str = DEFAULT_RERANKER_MODEL_NAME
    reranker_candidate_size: int = DEFAULT_RERANKER_CANDIDATE_SIZE
    reranker_batch_size: int = DEFAULT_RERANKER_BATCH_SIZE
    database_auto_create: bool = DEFAULT_DATABASE_AUTO_CREATE
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES
    max_upload_file_size: int = DEFAULT_MAX_UPLOAD_FILE_SIZE
    max_bulk_upload_size: int = DEFAULT_MAX_BULK_UPLOAD_SIZE
    max_bulk_file_count: int = DEFAULT_MAX_BULK_FILE_COUNT
    pdf_min_text_chars: int = DEFAULT_PDF_MIN_TEXT_CHARS
    pdf_ocr_enabled: bool = DEFAULT_PDF_OCR_ENABLED
    pdf_ocr_languages: str = DEFAULT_PDF_OCR_LANGUAGES
    pdf_ocr_dpi: int = DEFAULT_PDF_OCR_DPI
    pdf_ocr_timeout_seconds: int = DEFAULT_PDF_OCR_TIMEOUT_SECONDS
    pdf_ocr_max_pages: int = DEFAULT_PDF_OCR_MAX_PAGES
    pdf_text_extraction_timeout_seconds: int = (
        DEFAULT_PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS
    )
    security_headers_enabled: bool = DEFAULT_SECURITY_HEADERS_ENABLED
    rate_limit_enabled: bool = DEFAULT_RATE_LIMIT_ENABLED
    rate_limit_requests: int = DEFAULT_RATE_LIMIT_REQUESTS
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS
    code_repository_allowed_hosts: list[str] | None = None
    audit_log_enabled: bool = DEFAULT_AUDIT_LOG_ENABLED
    log_level: str = DEFAULT_LOG_LEVEL
    mcp_host: str = DEFAULT_MCP_HOST
    mcp_port: int = DEFAULT_MCP_PORT
    mcp_path: str = DEFAULT_MCP_PATH
    mcp_public_url: str = DEFAULT_MCP_PUBLIC_URL
    mcp_service_token_sha256: str = DEFAULT_MCP_SERVICE_TOKEN_SHA256
    mcp_service_account_email: str = DEFAULT_MCP_SERVICE_ACCOUNT_EMAIL


def get_settings() -> AppSettings:
    app_env = _read_str(name="APP_ENV", default=DEFAULT_APP_ENV).casefold()
    settings = AppSettings(
        app_env=app_env,
        document_chunk_size=_read_int(
            name="DOCUMENT_CHUNK_SIZE",
            default=DEFAULT_DOCUMENT_CHUNK_SIZE,
        ),
        document_chunk_overlap=_read_int(
            name="DOCUMENT_CHUNK_OVERLAP",
            default=DEFAULT_DOCUMENT_CHUNK_OVERLAP,
        ),
        embedding_model_name=_read_str(
            name="EMBEDDING_MODEL_NAME",
            default=DEFAULT_EMBEDDING_MODEL_NAME,
        ),
        qdrant_url=_read_str(
            name="QDRANT_URL",
            default=DEFAULT_QDRANT_URL,
        ),
        qdrant_collection_name=_read_str(
            name="QDRANT_COLLECTION_NAME",
            default=DEFAULT_QDRANT_COLLECTION_NAME,
        ),
        internal_generation_enabled=_read_bool(
            name="INTERNAL_GENERATION_ENABLED",
            default=DEFAULT_INTERNAL_GENERATION_ENABLED,
        ),
        ollama_base_url=_read_str(
            name="OLLAMA_BASE_URL",
            default=DEFAULT_OLLAMA_BASE_URL,
        ),
        ollama_model=_read_str(
            name="OLLAMA_MODEL",
            default=DEFAULT_OLLAMA_MODEL,
        ),
        database_url=_read_str(
            name="DATABASE_URL",
            default=DEFAULT_DATABASE_URL,
        ),
        jwt_secret_key=_read_str(
            name="JWT_SECRET_KEY",
            default=DEFAULT_JWT_SECRET_KEY,
        ),
        jwt_algorithm=_read_str(
            name="JWT_ALGORITHM",
            default=DEFAULT_JWT_ALGORITHM,
        ),
        jwt_access_token_expire_minutes=_read_int(
            name="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
            default=DEFAULT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        ),
        retrieval_mode=_read_str(
            name="RETRIEVAL_MODE",
            default=DEFAULT_RETRIEVAL_MODE,
        ),
        hybrid_fusion_strategy=_read_str(
            name="HYBRID_FUSION_STRATEGY",
            default=DEFAULT_HYBRID_FUSION_STRATEGY,
        ),
        hybrid_vector_weight=_read_float(
            name="HYBRID_VECTOR_WEIGHT",
            default=DEFAULT_HYBRID_VECTOR_WEIGHT,
        ),
        hybrid_bm25_weight=_read_float(
            name="HYBRID_BM25_WEIGHT",
            default=DEFAULT_HYBRID_BM25_WEIGHT,
        ),
        hybrid_candidate_multiplier=_read_int(
            name="HYBRID_CANDIDATE_MULTIPLIER",
            default=DEFAULT_HYBRID_CANDIDATE_MULTIPLIER,
        ),
        bm25_k1=_read_float(
            name="BM25_K1",
            default=DEFAULT_BM25_K1,
        ),
        bm25_b=_read_float(
            name="BM25_B",
            default=DEFAULT_BM25_B,
        ),
        reranker_enabled=_read_bool(
            name="RERANKER_ENABLED",
            default=DEFAULT_RERANKER_ENABLED,
        ),
        reranker_model_name=_read_str(
            name="RERANKER_MODEL_NAME",
            default=DEFAULT_RERANKER_MODEL_NAME,
        ),
        reranker_candidate_size=_read_int(
            name="RERANKER_CANDIDATE_SIZE",
            default=DEFAULT_RERANKER_CANDIDATE_SIZE,
        ),
        reranker_batch_size=_read_int(
            name="RERANKER_BATCH_SIZE",
            default=DEFAULT_RERANKER_BATCH_SIZE,
        ),
        database_auto_create=_read_bool(
            name="DATABASE_AUTO_CREATE",
            default=app_env not in PRODUCTION_ENV_NAMES,
        ),
        max_request_body_bytes=_read_int(
            name="MAX_REQUEST_BODY_BYTES",
            default=DEFAULT_MAX_REQUEST_BODY_BYTES,
        ),
        max_upload_file_size=_read_int_with_fallback(
            name="MAX_UPLOAD_FILE_SIZE",
            fallback_name="MAX_UPLOAD_BYTES",
            default=DEFAULT_MAX_UPLOAD_FILE_SIZE,
        ),
        max_bulk_upload_size=_read_int(
            name="MAX_BULK_UPLOAD_SIZE",
            default=DEFAULT_MAX_BULK_UPLOAD_SIZE,
        ),
        max_bulk_file_count=_read_int(
            name="MAX_BULK_FILE_COUNT",
            default=DEFAULT_MAX_BULK_FILE_COUNT,
        ),
        pdf_min_text_chars=_read_int(
            name="PDF_MIN_TEXT_CHARS",
            default=DEFAULT_PDF_MIN_TEXT_CHARS,
        ),
        pdf_ocr_enabled=_read_bool(
            name="PDF_OCR_ENABLED",
            default=DEFAULT_PDF_OCR_ENABLED,
        ),
        pdf_ocr_languages=_read_str(
            name="PDF_OCR_LANGUAGES",
            default=DEFAULT_PDF_OCR_LANGUAGES,
        ),
        pdf_ocr_dpi=_read_int(
            name="PDF_OCR_DPI",
            default=DEFAULT_PDF_OCR_DPI,
        ),
        pdf_ocr_timeout_seconds=_read_int(
            name="PDF_OCR_TIMEOUT_SECONDS",
            default=DEFAULT_PDF_OCR_TIMEOUT_SECONDS,
        ),
        pdf_ocr_max_pages=_read_int(
            name="PDF_OCR_MAX_PAGES",
            default=DEFAULT_PDF_OCR_MAX_PAGES,
        ),
        pdf_text_extraction_timeout_seconds=_read_int(
            name="PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS",
            default=DEFAULT_PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS,
        ),
        security_headers_enabled=_read_bool(
            name="SECURITY_HEADERS_ENABLED",
            default=DEFAULT_SECURITY_HEADERS_ENABLED,
        ),
        rate_limit_enabled=_read_bool(
            name="RATE_LIMIT_ENABLED",
            default=DEFAULT_RATE_LIMIT_ENABLED,
        ),
        rate_limit_requests=_read_int(
            name="RATE_LIMIT_REQUESTS",
            default=DEFAULT_RATE_LIMIT_REQUESTS,
        ),
        rate_limit_window_seconds=_read_int(
            name="RATE_LIMIT_WINDOW_SECONDS",
            default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        ),
        code_repository_allowed_hosts=_read_csv(
            name="CODE_REPOSITORY_ALLOWED_HOSTS",
            default=DEFAULT_CODE_REPOSITORY_ALLOWED_HOSTS,
        ),
        audit_log_enabled=_read_bool(
            name="AUDIT_LOG_ENABLED",
            default=DEFAULT_AUDIT_LOG_ENABLED,
        ),
        log_level=_read_str(
            name="LOG_LEVEL",
            default=DEFAULT_LOG_LEVEL,
        ).upper(),
        mcp_host=_read_str(
            name="MCP_HOST",
            default=DEFAULT_MCP_HOST,
        ),
        mcp_port=_read_int(
            name="MCP_PORT",
            default=DEFAULT_MCP_PORT,
        ),
        mcp_path=_read_str(
            name="MCP_PATH",
            default=DEFAULT_MCP_PATH,
        ),
        mcp_public_url=_read_str(
            name="MCP_PUBLIC_URL",
            default=DEFAULT_MCP_PUBLIC_URL,
        ),
        mcp_service_token_sha256=_read_str(
            name="MCP_SERVICE_TOKEN_SHA256",
            default=DEFAULT_MCP_SERVICE_TOKEN_SHA256,
        ).casefold(),
        mcp_service_account_email=_read_str(
            name="MCP_SERVICE_ACCOUNT_EMAIL",
            default=DEFAULT_MCP_SERVICE_ACCOUNT_EMAIL,
        ).casefold(),
    )
    _validate_app_settings(settings)
    _validate_chunk_settings(settings)
    _validate_embedding_settings(settings)
    _validate_qdrant_settings(settings)
    _validate_ollama_settings(settings)
    _validate_database_settings(settings)
    _validate_auth_settings(settings)
    _validate_retrieval_settings(settings)
    _validate_security_settings(settings)
    _validate_mcp_settings(settings)
    return settings


def _read_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _read_int_with_fallback(name: str, fallback_name: str, default: int) -> int:
    if os.getenv(name) is not None:
        return _read_int(name=name, default=default)

    return _read_int(name=fallback_name, default=default)


def _read_str(name: str, default: str) -> str:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip()


def _read_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc


def _read_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().casefold()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True

    if normalized_value in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean value.")


def _read_csv(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return list(default)

    return [
        item
        for item in (part.strip().casefold() for part in raw_value.split(","))
        if item
    ]


def _validate_app_settings(settings: AppSettings) -> None:
    if not settings.app_env:
        raise ValueError("APP_ENV cannot be empty.")


def _validate_chunk_settings(settings: AppSettings) -> None:
    if settings.document_chunk_size < 1:
        raise ValueError("DOCUMENT_CHUNK_SIZE must be greater than 0.")

    if settings.document_chunk_overlap < 0:
        raise ValueError("DOCUMENT_CHUNK_OVERLAP cannot be negative.")

    if settings.document_chunk_overlap >= settings.document_chunk_size:
        raise ValueError(
            "DOCUMENT_CHUNK_OVERLAP must be smaller than DOCUMENT_CHUNK_SIZE."
        )


def _validate_embedding_settings(settings: AppSettings) -> None:
    if not settings.embedding_model_name:
        raise ValueError("EMBEDDING_MODEL_NAME cannot be empty.")


def _validate_qdrant_settings(settings: AppSettings) -> None:
    if not settings.qdrant_url:
        raise ValueError("QDRANT_URL cannot be empty.")

    if not settings.qdrant_collection_name:
        raise ValueError("QDRANT_COLLECTION_NAME cannot be empty.")


def _validate_ollama_settings(settings: AppSettings) -> None:
    if not settings.internal_generation_enabled:
        return

    if not settings.ollama_base_url:
        raise ValueError(
            "OLLAMA_BASE_URL cannot be empty when "
            "INTERNAL_GENERATION_ENABLED is true."
        )

    if not settings.ollama_model:
        raise ValueError(
            "OLLAMA_MODEL cannot be empty when INTERNAL_GENERATION_ENABLED "
            "is true."
        )


def _validate_database_settings(settings: AppSettings) -> None:
    if not settings.database_url:
        raise ValueError("DATABASE_URL cannot be empty.")

    if settings.app_env in PRODUCTION_ENV_NAMES and settings.database_auto_create:
        raise ValueError(
            "DATABASE_AUTO_CREATE must be false in production. "
            "Run Alembic migrations before starting the API."
        )


def _validate_auth_settings(settings: AppSettings) -> None:
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY cannot be empty.")

    if not settings.jwt_algorithm:
        raise ValueError("JWT_ALGORITHM cannot be empty.")

    if settings.jwt_access_token_expire_minutes < 1:
        raise ValueError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0.")

    if settings.app_env in PRODUCTION_ENV_NAMES:
        if settings.jwt_secret_key == DEFAULT_JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY must be changed in production.")

        if len(settings.jwt_secret_key) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters in production."
            )


def _validate_retrieval_settings(settings: AppSettings) -> None:
    if settings.retrieval_mode not in {"vector", "bm25", "hybrid"}:
        raise ValueError("RETRIEVAL_MODE must be vector, bm25, or hybrid.")

    if settings.hybrid_fusion_strategy not in {"rrf", "weighted_score"}:
        raise ValueError(
            "HYBRID_FUSION_STRATEGY must be rrf or weighted_score."
        )

    if settings.hybrid_vector_weight < 0:
        raise ValueError("HYBRID_VECTOR_WEIGHT cannot be negative.")

    if settings.hybrid_bm25_weight < 0:
        raise ValueError("HYBRID_BM25_WEIGHT cannot be negative.")

    if settings.hybrid_vector_weight == 0 and settings.hybrid_bm25_weight == 0:
        raise ValueError(
            "At least one of HYBRID_VECTOR_WEIGHT or HYBRID_BM25_WEIGHT "
            "must be greater than 0."
        )

    if settings.hybrid_candidate_multiplier < 1:
        raise ValueError("HYBRID_CANDIDATE_MULTIPLIER must be greater than 0.")

    if settings.bm25_k1 <= 0:
        raise ValueError("BM25_K1 must be greater than 0.")

    if settings.bm25_b < 0 or settings.bm25_b > 1:
        raise ValueError("BM25_B must be between 0 and 1.")

    if not settings.reranker_model_name:
        raise ValueError("RERANKER_MODEL_NAME cannot be empty.")

    if settings.reranker_candidate_size < 1:
        raise ValueError("RERANKER_CANDIDATE_SIZE must be greater than 0.")

    if settings.reranker_batch_size < 1:
        raise ValueError("RERANKER_BATCH_SIZE must be greater than 0.")


def _validate_security_settings(settings: AppSettings) -> None:
    if settings.max_request_body_bytes < 1:
        raise ValueError("MAX_REQUEST_BODY_BYTES must be greater than 0.")

    if settings.max_upload_file_size < 1:
        raise ValueError("MAX_UPLOAD_FILE_SIZE must be greater than 0.")

    if settings.max_bulk_upload_size < 1:
        raise ValueError("MAX_BULK_UPLOAD_SIZE must be greater than 0.")

    if settings.max_bulk_file_count < 1:
        raise ValueError("MAX_BULK_FILE_COUNT must be greater than 0.")

    if settings.max_upload_file_size > settings.max_request_body_bytes:
        raise ValueError(
            "MAX_UPLOAD_FILE_SIZE must be less than or equal to "
            "MAX_REQUEST_BODY_BYTES."
        )

    if settings.max_upload_file_size > settings.max_bulk_upload_size:
        raise ValueError(
            "MAX_UPLOAD_FILE_SIZE must be less than or equal to "
            "MAX_BULK_UPLOAD_SIZE."
        )

    if settings.pdf_min_text_chars < 1:
        raise ValueError("PDF_MIN_TEXT_CHARS must be greater than 0.")

    if not settings.pdf_ocr_languages:
        raise ValueError("PDF_OCR_LANGUAGES cannot be empty.")

    if settings.pdf_ocr_dpi < 72:
        raise ValueError("PDF_OCR_DPI must be at least 72.")

    if settings.pdf_ocr_timeout_seconds < 1:
        raise ValueError("PDF_OCR_TIMEOUT_SECONDS must be greater than 0.")

    if settings.pdf_ocr_max_pages < 1:
        raise ValueError("PDF_OCR_MAX_PAGES must be greater than 0.")

    if settings.pdf_text_extraction_timeout_seconds < 1:
        raise ValueError(
            "PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS must be greater than 0."
        )

    if settings.rate_limit_requests < 1:
        raise ValueError("RATE_LIMIT_REQUESTS must be greater than 0.")

    if settings.rate_limit_window_seconds < 1:
        raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be greater than 0.")

    allowed_hosts = settings.code_repository_allowed_hosts or []
    if settings.app_env in PRODUCTION_ENV_NAMES and (
        not allowed_hosts or "*" in allowed_hosts
    ):
        raise ValueError(
            "CODE_REPOSITORY_ALLOWED_HOSTS must be explicitly configured in "
            "production."
        )

    if settings.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")


def _validate_mcp_settings(settings: AppSettings) -> None:
    if not settings.mcp_host:
        raise ValueError("MCP_HOST cannot be empty.")

    if settings.mcp_port < 1 or settings.mcp_port > 65535:
        raise ValueError("MCP_PORT must be between 1 and 65535.")

    if not settings.mcp_path.startswith("/"):
        raise ValueError("MCP_PATH must start with '/'.")

    if not settings.mcp_public_url.startswith(("http://", "https://")):
        raise ValueError("MCP_PUBLIC_URL must start with http:// or https://.")

    if settings.mcp_service_token_sha256 and (
        len(settings.mcp_service_token_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in settings.mcp_service_token_sha256
        )
    ):
        raise ValueError("MCP_SERVICE_TOKEN_SHA256 must be a SHA-256 hex digest.")
