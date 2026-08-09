from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CodeChunkRecord,
    CodeFileRecord,
    CodeRepositoryPermissionRecord,
    CodeRepositoryRecord,
    DocumentChunkRecord,
    DocumentPermissionRecord,
    DocumentRecord,
    DocumentStatus,
    RAGFeedbackRecord,
    RAGTraceRecord,
    UserRecord,
)


def test_document_chunk_relationship() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        document = DocumentRecord(
            filename="security.md",
            file_type="markdown",
            storage_path="security.md",
            file_hash="a" * 64,
            status=DocumentStatus.INDEXED.value,
        )
        document.chunks.append(
            DocumentChunkRecord(
                qdrant_point_id="point-1",
                chunk_index=1,
                page_number=None,
                start_char=0,
                end_char=120,
            )
        )
        session.add(document)
        session.commit()

        stored_document = session.scalars(select(DocumentRecord)).one()
        assert stored_document.status == DocumentStatus.INDEXED.value
        assert len(stored_document.chunks) == 1
        assert stored_document.chunks[0].document is stored_document
        assert stored_document.chunks[0].qdrant_point_id == "point-1"


def test_document_permission_relationship() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        user = UserRecord(
            email="admin@example.com",
            password_hash="$argon2id$hash",
        )
        document = DocumentRecord(
            filename="security.md",
            file_type="markdown",
            storage_path="security.md",
            file_hash="a" * 64,
            status=DocumentStatus.INDEXED.value,
        )
        permission = DocumentPermissionRecord(user=user, document=document)
        session.add(permission)
        session.commit()

        stored_permission = session.scalars(select(DocumentPermissionRecord)).one()
        assert stored_permission.user.email == "admin@example.com"
        assert stored_permission.document.filename == "security.md"
        assert stored_permission in stored_permission.user.document_permissions
        assert stored_permission in stored_permission.document.permissions


def test_code_repository_file_chunk_and_permission_relationships() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        user = UserRecord(
            email="developer@example.com",
            password_hash="$argon2id$hash",
        )
        repository = CodeRepositoryRecord(
            repo_url="file:///repo",
            repo_name="repo",
            branch="main",
            commit_sha="a" * 40,
            storage_path="repo/main/aaaaaaaa",
            status=DocumentStatus.INDEXED.value,
        )
        code_file = CodeFileRecord(
            repository=repository,
            file_path="app.py",
            language="python",
            file_hash="b" * 64,
            size_bytes=100,
        )
        code_file.chunks.append(
            CodeChunkRecord(
                repository=repository,
                qdrant_point_id="code-point-1",
                chunk_index=1,
                symbol_name="hello",
                symbol_kind="function",
                start_line=1,
                end_line=3,
                start_char=0,
                end_char=80,
            )
        )
        permission = CodeRepositoryPermissionRecord(
            user=user,
            repository=repository,
        )
        session.add(permission)
        session.commit()

        stored_repository = session.scalars(select(CodeRepositoryRecord)).one()
        assert stored_repository.files[0].file_path == "app.py"
        assert stored_repository.chunks[0].qdrant_point_id == "code-point-1"
        assert stored_repository.permissions[0].user.email == "developer@example.com"
        assert stored_repository.files[0].chunks[0].repository is stored_repository


def test_rag_trace_record_creation() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        trace = RAGTraceRecord(
            request_id="req-1",
            user_id=1,
            question="What is the remote work policy?",
            retrieval_mode="hybrid",
            retrieval_time_ms=12.5,
            reranker_time_ms=4.2,
            generation_time_ms=30.1,
            total_time_ms=50.4,
            model_name="llama3.1:8b",
            retrieved_count=1,
            status="SUCCESS",
            retrieved_sources=[
                {
                    "filename": "company_policy.md",
                    "score": 0.91,
                    "vector_score": 0.91,
                    "bm25_score": None,
                    "fusion_score": None,
                    "reranker_score": None,
                }
            ],
        )
        session.add(trace)
        session.commit()

        stored_trace = session.scalars(select(RAGTraceRecord)).one()
        assert stored_trace.request_id == "req-1"
        assert stored_trace.retrieved_count == 1
        assert stored_trace.status == "SUCCESS"
        assert stored_trace.retrieved_sources[0]["filename"] == "company_policy.md"


def test_rag_feedback_relationship() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        user = UserRecord(
            email="admin@example.com",
            password_hash="$argon2id$hash",
        )
        trace = RAGTraceRecord(
            request_id="req-1",
            user_id=1,
            question="What is the remote work policy?",
            retrieval_mode="hybrid",
            model_name="llama3.1:8b",
            retrieved_count=1,
            status="SUCCESS",
            retrieved_sources=[],
        )
        feedback = RAGFeedbackRecord(
            trace=trace,
            user=user,
            rating=5,
            comment="Accurate answer.",
        )
        session.add(feedback)
        session.commit()

        stored_feedback = session.scalars(select(RAGFeedbackRecord)).one()
        assert stored_feedback.trace.request_id == "req-1"
        assert stored_feedback.user.email == "admin@example.com"
        assert stored_feedback.rating == 5
        assert stored_feedback in stored_feedback.trace.feedback
        assert stored_feedback in stored_feedback.user.rag_feedback
