from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RAGTraceRecord
from app.schemas.documents import ChunkMetadata, RetrievalResult
from app.services.rag_trace_service import RAGTraceService
from app.services.trace_context import RAGTraceContext


def _build_trace_service():
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return (
        RAGTraceService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        session_factory,
    )


def _build_retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        text="Remote work policy text.",
        filename="company_policy.md",
        page_number=None,
        score=0.91,
        vector_score=0.82,
        bm25_score=1.7,
        fusion_score=0.45,
        reranker_score=0.91,
        metadata=ChunkMetadata(
            filename="company_policy.md",
            source_path="company_policy.md",
            file_type="markdown",
            page_number=None,
            chunk_index=2,
            start_char=10,
            end_char=34,
        ),
    )


def test_rag_trace_service_persists_trace_with_retrieved_source_debug_info() -> None:
    trace_service, session_factory = _build_trace_service()
    trace_context = RAGTraceContext(
        request_id="req-1",
        user_id=1,
        question="What is the remote work policy?",
        retrieval_mode="hybrid",
        model_name="llama3.1:8b",
    )
    trace_context.retrieval_time_ms = 12.3
    trace_context.reranker_time_ms = 4.5
    trace_context.generation_time_ms = 30.4
    trace_context.prompt_tokens = None
    trace_context.completion_tokens = None
    trace_context.record_retrieved_sources([_build_retrieval_result()])
    trace_context.finish_success()

    stored_trace = trace_service.save_trace(trace_context)

    with session_factory() as session:
        record = session.scalars(select(RAGTraceRecord)).one()
        assert stored_trace.id == record.id
        assert record.request_id == "req-1"
        assert record.user_id == 1
        assert record.retrieval_mode == "hybrid"
        assert record.model_name == "llama3.1:8b"
        assert record.retrieved_count == 1
        assert record.status == "SUCCESS"
        assert record.error_message is None
        assert record.prompt_tokens is None
        assert record.completion_tokens is None
        assert record.retrieved_sources == [
            {
                "content_type": "document",
                "file_type": "markdown",
                "filename": "company_policy.md",
                "source_path": "company_policy.md",
                "page_number": None,
                "section_heading": None,
                "heading_path": None,
                "workbook": None,
                "sheet_name": None,
                "cell_range": None,
                "row_start": None,
                "row_end": None,
                "slide_number": None,
                "slide_title": None,
                "chunk_index": 2,
                "repo_name": None,
                "repo_url": None,
                "branch": None,
                "commit_sha": None,
                "language": None,
                "symbol_name": None,
                "symbol_kind": None,
                "start_line": None,
                "end_line": None,
                "repository_file_path": None,
                "score": 0.91,
                "vector_score": 0.82,
                "bm25_score": 1.7,
                "fusion_score": 0.45,
                "reranker_score": 0.91,
            }
        ]


def test_rag_trace_service_persists_error_status() -> None:
    trace_service, session_factory = _build_trace_service()
    trace_context = RAGTraceContext(
        request_id="req-error",
        user_id=2,
        question="",
        retrieval_mode="vector",
        model_name="llama3.1:8b",
    )
    trace_context.finish_error("Question cannot be empty.")

    trace_service.save_trace(trace_context)

    with session_factory() as session:
        record = session.scalars(select(RAGTraceRecord)).one()
        assert record.request_id == "req-error"
        assert record.status == "ERROR"
        assert record.error_message == "Question cannot be empty."
        assert record.retrieved_count == 0
