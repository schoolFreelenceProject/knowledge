from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.db.session import get_database_engine, get_session_factory, init_db
from app.services.bm25_retrieval_service import BM25Config, BM25RetrievalService
from app.services.chat_service import RAGChatService
from app.services.code_chunker import CodeChunkingConfig
from app.services.code_ingestion_service import CodeIngestionService
from app.services.code_metadata_service import CodeMetadataService
from app.services.code_parser import TreeSitterCodeParser
from app.services.code_repository_management_service import (
    CodeRepositoryManagementService,
)
from app.services.code_repository_loader import GitRepositoryLoader
from app.services.document_management_service import DocumentManagementService
from app.services.document_loader import PdfExtractionConfig
from app.services.embedding_service import SentenceTransformersEmbeddingService
from app.services.generation_service import (
    OllamaGenerationService,
    RAGGenerationService,
)
from app.services.health_service import HealthService
from app.services.hybrid_fusion_service import (
    HybridFusionConfig,
    HybridFusionService,
)
from app.services.ingestion_service import IngestionService
from app.services.knowledge_tool_service import KnowledgeToolService
from app.services.knowledge_explorer_service import KnowledgeExplorerService
from app.services.metadata_service import DocumentMetadataService
from app.services.permission_service import PermissionService
from app.services.prompt_builder import RAGPromptBuilder
from app.services.rag_feedback_service import RAGFeedbackService
from app.services.rag_analytics_service import RAGAnalyticsService
from app.services.rag_trace_service import RAGTraceService
from app.services.reranker_service import CrossEncoderRerankerService, RerankerConfig
from app.services.retrieval_service import RetrievalConfig, RetrievalService
from app.services.text_chunker import ChunkingConfig
from app.services.vector_store import QdrantVectorStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
REPOSITORIES_DIR = PROJECT_ROOT / "data" / "repositories"


@lru_cache
def get_retrieval_service() -> RetrievalService:
    settings = get_settings()
    embedding_service = SentenceTransformersEmbeddingService(
        model_name=settings.embedding_model_name,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
    )
    return RetrievalService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        bm25_retrieval_service=BM25RetrievalService(
            vector_store=vector_store,
            config=BM25Config(
                k1=settings.bm25_k1,
                b=settings.bm25_b,
            ),
        ),
        hybrid_fusion_service=HybridFusionService(
            config=HybridFusionConfig(
                strategy=settings.hybrid_fusion_strategy,
                vector_weight=settings.hybrid_vector_weight,
                bm25_weight=settings.hybrid_bm25_weight,
            ),
        ),
        reranker_service=CrossEncoderRerankerService(
            config=RerankerConfig(
                model_name=settings.reranker_model_name,
                batch_size=settings.reranker_batch_size,
            ),
        ),
        config=RetrievalConfig(
            mode=settings.retrieval_mode,
            hybrid_candidate_multiplier=settings.hybrid_candidate_multiplier,
            reranker_enabled=settings.reranker_enabled,
            reranker_candidate_size=settings.reranker_candidate_size,
        ),
    )


@lru_cache
def get_chat_service() -> RAGChatService:
    settings = get_settings()
    generation_service = None
    if settings.internal_generation_enabled:
        generation_service = RAGGenerationService(
            ollama_service=OllamaGenerationService(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            ),
            prompt_builder=RAGPromptBuilder(),
        )

    return RAGChatService(
        retrieval_service=get_retrieval_service(),
        generation_service=generation_service,
    )


@lru_cache
def get_permission_service() -> PermissionService:
    return PermissionService(
        session_factory=get_session_factory(),
        init_database=init_db,
    )


@lru_cache
def get_rag_trace_service() -> RAGTraceService:
    return RAGTraceService(
        session_factory=get_session_factory(),
        init_database=init_db,
    )


@lru_cache
def get_rag_feedback_service() -> RAGFeedbackService:
    return RAGFeedbackService(
        session_factory=get_session_factory(),
        init_database=init_db,
    )


@lru_cache
def get_rag_analytics_service() -> RAGAnalyticsService:
    return RAGAnalyticsService(
        session_factory=get_session_factory(),
        init_database=init_db,
    )


@lru_cache
def get_ingestion_service() -> IngestionService:
    settings = get_settings()
    chunk_config = ChunkingConfig(
        chunk_size=settings.document_chunk_size,
        chunk_overlap=settings.document_chunk_overlap,
    )
    embedding_service = SentenceTransformersEmbeddingService(
        model_name=settings.embedding_model_name,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
    )
    metadata_service = DocumentMetadataService(
        session_factory=get_session_factory(),
        init_database=init_db,
    )
    permission_service = get_permission_service()

    return IngestionService(
        documents_dir=DOCUMENTS_DIR,
        chunk_config=chunk_config,
        embedding_service=embedding_service,
        vector_store=vector_store,
        metadata_service=metadata_service,
        permission_service=permission_service,
        max_upload_bytes=settings.max_upload_file_size,
        pdf_extraction_config=_build_pdf_extraction_config(settings),
        retrieval_index_refresh=_refresh_retrieval_indexes,
    )


@lru_cache
def get_code_ingestion_service() -> CodeIngestionService:
    settings = get_settings()
    embedding_service = SentenceTransformersEmbeddingService(
        model_name=settings.embedding_model_name,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
    )
    return CodeIngestionService(
        repository_loader=GitRepositoryLoader(
            repositories_dir=REPOSITORIES_DIR,
            allowed_hosts=settings.code_repository_allowed_hosts,
        ),
        parser=TreeSitterCodeParser(),
        chunk_config=CodeChunkingConfig(
            max_chunk_chars=settings.document_chunk_size,
            overlap_lines=max(0, settings.document_chunk_overlap // 80),
        ),
        embedding_service=embedding_service,
        vector_store=vector_store,
        metadata_service=CodeMetadataService(
            session_factory=get_session_factory(),
            init_database=init_db,
        ),
        permission_service=get_permission_service(),
    )


@lru_cache
def get_code_repository_management_service() -> CodeRepositoryManagementService:
    settings = get_settings()
    embedding_service = SentenceTransformersEmbeddingService(
        model_name=settings.embedding_model_name,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
    )
    repository_loader = GitRepositoryLoader(
        repositories_dir=REPOSITORIES_DIR,
        allowed_hosts=settings.code_repository_allowed_hosts,
    )
    return CodeRepositoryManagementService(
        repositories_dir=REPOSITORIES_DIR,
        repository_loader=repository_loader,
        parser=TreeSitterCodeParser(),
        chunk_config=CodeChunkingConfig(
            max_chunk_chars=settings.document_chunk_size,
            overlap_lines=max(0, settings.document_chunk_overlap // 80),
        ),
        embedding_service=embedding_service,
        vector_store=vector_store,
        metadata_service=CodeMetadataService(
            session_factory=get_session_factory(),
            init_database=init_db,
        ),
    )


@lru_cache
def get_document_management_service() -> DocumentManagementService:
    settings = get_settings()
    chunk_config = ChunkingConfig(
        chunk_size=settings.document_chunk_size,
        chunk_overlap=settings.document_chunk_overlap,
    )
    embedding_service = SentenceTransformersEmbeddingService(
        model_name=settings.embedding_model_name,
    )
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
    )
    metadata_service = DocumentMetadataService(
        session_factory=get_session_factory(),
        init_database=init_db,
    )

    return DocumentManagementService(
        documents_dir=DOCUMENTS_DIR,
        chunk_config=chunk_config,
        embedding_service=embedding_service,
        vector_store=vector_store,
        metadata_service=metadata_service,
        pdf_extraction_config=_build_pdf_extraction_config(settings),
        retrieval_index_refresh=_refresh_retrieval_indexes,
    )


@lru_cache
def get_knowledge_tool_service() -> KnowledgeToolService:
    chat_service = get_chat_service()
    return KnowledgeToolService(
        chat_service=chat_service,
        retrieval_service=get_retrieval_service(),
        permission_service=get_permission_service(),
        document_management_service=get_document_management_service(),
        trace_service=get_rag_trace_service(),
    )


@lru_cache
def get_knowledge_explorer_service() -> KnowledgeExplorerService:
    return KnowledgeExplorerService(
        retrieval_service=get_retrieval_service(),
        permission_service=get_permission_service(),
        document_metadata_service=DocumentMetadataService(
            session_factory=get_session_factory(),
            init_database=init_db,
        ),
        code_metadata_service=CodeMetadataService(
            session_factory=get_session_factory(),
            init_database=init_db,
        ),
        documents_dir=DOCUMENTS_DIR,
        repositories_dir=REPOSITORIES_DIR,
    )


@lru_cache
def get_health_service() -> HealthService:
    settings = get_settings()
    return HealthService(
        database_engine_factory=get_database_engine,
        qdrant_url=settings.qdrant_url,
        ollama_base_url=settings.ollama_base_url,
        internal_generation_enabled=settings.internal_generation_enabled,
    )


def _build_pdf_extraction_config(settings) -> PdfExtractionConfig:
    return PdfExtractionConfig(
        min_text_chars=settings.pdf_min_text_chars,
        ocr_enabled=settings.pdf_ocr_enabled,
        ocr_languages=settings.pdf_ocr_languages,
        ocr_dpi=settings.pdf_ocr_dpi,
        ocr_timeout_seconds=settings.pdf_ocr_timeout_seconds,
        ocr_max_pages=settings.pdf_ocr_max_pages,
        text_extraction_timeout_seconds=(
            settings.pdf_text_extraction_timeout_seconds
        ),
    )


def _refresh_retrieval_indexes() -> None:
    retrieval_service = get_retrieval_service()
    bm25_service = retrieval_service.bm25_retrieval_service
    if bm25_service is not None:
        bm25_service.rebuild_index()
