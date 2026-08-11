from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CodeChunkRecord,
    CodeFileRecord,
    CodeRepositoryPermissionRecord,
    CodeRepositoryRecord,
    CodeSourceType,
    DocumentChunkRecord,
    DocumentPermissionRecord,
    DocumentRecord,
    DocumentStatus,
    UserRecord,
)
from app.schemas.documents import ChunkMetadata, RetrievalResult
from app.schemas.knowledge_explorer import KnowledgeSearchRequest
from app.services.code_metadata_service import CodeMetadataService
from app.services.knowledge_explorer_service import KnowledgeExplorerService
from app.services.metadata_service import DocumentMetadataService
from app.services.permission_service import PermissionService


class FakeRetrievalService:
    config = SimpleNamespace(mode="hybrid")

    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def retrieve(
        self,
        query,
        top_k,
        allowed_point_ids=None,
        content_types=None,
        languages=None,
    ):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "allowed_point_ids": allowed_point_ids,
                "content_types": content_types,
                "languages": languages,
            }
        )
        allowed_point_id_set = (
            set(allowed_point_ids)
            if allowed_point_ids is not None
            else None
        )
        content_type_set = (
            set(content_types)
            if content_types is not None
            else None
        )
        language_set = (
            {language.casefold() for language in languages}
            if languages is not None
            else None
        )
        filtered_results = [
            result
            for result in self.results
            if (
                allowed_point_id_set is None
                or result.point_id in allowed_point_id_set
            )
            and (
                content_type_set is None
                or result.content_type in content_type_set
            )
            and (
                language_set is None
                or (
                    result.metadata.language
                    and result.metadata.language.casefold() in language_set
                )
            )
        ]
        return filtered_results[:top_k]


def _build_services(tmp_path, results: list[RetrievalResult]):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    _seed_metadata(session_factory=session_factory, tmp_path=tmp_path)
    retrieval_service = FakeRetrievalService(results=results)
    explorer_service = KnowledgeExplorerService(
        retrieval_service=retrieval_service,
        permission_service=PermissionService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        document_metadata_service=DocumentMetadataService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        code_metadata_service=CodeMetadataService(
            session_factory=session_factory,
            init_database=lambda: Base.metadata.create_all(bind=engine),
        ),
        documents_dir=tmp_path / "documents",
        repositories_dir=tmp_path / "repositories",
    )
    return explorer_service, retrieval_service


def _seed_metadata(session_factory, tmp_path) -> None:
    code_path = (
        tmp_path
        / "repositories"
        / "local"
        / "LocalCode"
        / ("f" * 16)
        / "src"
        / "app.py"
    )
    code_path.parent.mkdir(parents=True)
    code_path.write_text(
        "\n".join(
            [
                "def helper():",
                "    return 'setup'",
                "",
                "def launch():",
                "    policy = 'remote work'",
                "    return policy",
                "",
                "print(launch())",
            ]
        ),
        encoding="utf-8",
    )
    with session_factory() as session:
        session.add_all(
            [
                UserRecord(
                    id=7,
                    email="searcher@example.com",
                    password_hash="$argon2id$hash",
                ),
                UserRecord(
                    id=8,
                    email="restricted@example.com",
                    password_hash="$argon2id$hash",
                ),
            ]
        )
        document = DocumentRecord(
            id=1,
            filename="HR/leave.md",
            file_type="markdown",
            storage_path="HR/leave.md",
            file_hash="a" * 64,
            status=DocumentStatus.INDEXED.value,
        )
        private_document = DocumentRecord(
            id=2,
            filename="Finance/private.md",
            file_type="markdown",
            storage_path="Finance/private.md",
            file_hash="b" * 64,
            status=DocumentStatus.INDEXED.value,
        )
        repository = CodeRepositoryRecord(
            id=10,
            source_type=CodeSourceType.LOCAL_FOLDER.value,
            repo_url=None,
            repo_name="LocalCode",
            branch=None,
            commit_sha=None,
            source_fingerprint="f" * 64,
            storage_path=f"local/LocalCode/{'f' * 16}",
            status=DocumentStatus.INDEXED.value,
        )
        session.add_all([document, private_document, repository])
        session.flush()
        code_file = CodeFileRecord(
            id=20,
            repository_id=repository.id,
            file_path="src/app.py",
            language="python",
            file_hash="c" * 64,
            size_bytes=120,
        )
        session.add(code_file)
        session.flush()
        session.add_all(
            [
                DocumentChunkRecord(
                    document_id=document.id,
                    qdrant_point_id="doc-point-1",
                    chunk_index=1,
                    page_number=None,
                    start_char=0,
                    end_char=42,
                ),
                DocumentChunkRecord(
                    document_id=private_document.id,
                    qdrant_point_id="private-doc-point",
                    chunk_index=1,
                    page_number=None,
                    start_char=0,
                    end_char=24,
                ),
                CodeChunkRecord(
                    repository_id=repository.id,
                    code_file_id=code_file.id,
                    qdrant_point_id="code-point-1",
                    chunk_index=1,
                    symbol_name="launch",
                    symbol_kind="function",
                    start_line=4,
                    end_line=6,
                    start_char=32,
                    end_char=96,
                ),
                DocumentPermissionRecord(document_id=document.id, user_id=7),
                CodeRepositoryPermissionRecord(
                    repository_id=repository.id,
                    user_id=7,
                ),
            ]
        )
        session.commit()


def _document_result(point_id: str = "doc-point-1") -> RetrievalResult:
    return RetrievalResult(
        point_id=point_id,
        text="Employees may request remote work leave in the HR policy.",
        filename="HR/leave.md",
        page_number=None,
        score=0.82,
        bm25_score=1.4,
        content_type="document",
        metadata=ChunkMetadata(
            filename="HR/leave.md",
            source_path="HR/leave.md",
            file_type="markdown",
            content_type="document",
            page_number=None,
            chunk_index=1,
            start_char=0,
            end_char=56,
        ),
    )


def _code_result() -> RetrievalResult:
    return RetrievalResult(
        point_id="code-point-1",
        text="def launch():\n    policy = 'remote work'\n    return policy",
        filename="src/app.py",
        page_number=None,
        score=0.91,
        vector_score=0.9,
        content_type="code",
        metadata=ChunkMetadata(
            filename="src/app.py",
            source_path="LocalCode@local-ffffffffffff/src/app.py",
            file_type="code",
            content_type="code",
            page_number=None,
            chunk_index=1,
            start_char=32,
            end_char=96,
            repo_name="LocalCode",
            source_type="LOCAL_FOLDER",
            language="python",
            symbol_name="launch",
            symbol_kind="function",
            start_line=4,
            end_line=6,
            repository_file_path="src/app.py",
        ),
    )


def test_document_search_returns_document_metadata_and_preview(tmp_path) -> None:
    service, retrieval_service = _build_services(tmp_path, [_document_result()])

    response = service.search(
        KnowledgeSearchRequest(query="remote work", mode="documents", top_k=5),
        user_id=7,
    )

    assert response.retrieval_mode == "hybrid"
    assert retrieval_service.calls[0]["content_types"] == ["document"]
    assert response.results[0].content_type == "document"
    assert response.results[0].document_id == 1
    assert response.results[0].filename == "HR/leave.md"
    assert response.results[0].chunk_index == 1
    assert "remote work leave" in response.results[0].preview
    assert response.results[0].inspection.text.startswith("Employees may request")


def test_code_search_returns_code_metadata_and_surrounding_lines(tmp_path) -> None:
    service, retrieval_service = _build_services(tmp_path, [_code_result()])

    response = service.search(
        KnowledgeSearchRequest(query="launch", mode="code", top_k=3),
        user_id=7,
    )

    assert retrieval_service.calls[0]["content_types"] == ["code"]
    result = response.results[0]
    assert result.content_type == "code"
    assert result.repository_id == 10
    assert result.repo_name == "LocalCode"
    assert result.file_path == "src/app.py"
    assert result.language == "python"
    assert result.symbol_name == "launch"
    assert result.start_line == 4
    assert result.end_line == 6
    assert "   4 def launch():" in result.inspection.text
    assert "   8 print(launch())" in result.inspection.text
    assert result.inspection.highlight_start_line == 4


def test_combined_search_returns_document_and_code_results(tmp_path) -> None:
    service, retrieval_service = _build_services(
        tmp_path,
        [_code_result(), _document_result()],
    )

    response = service.search(
        KnowledgeSearchRequest(query="remote", mode="all", top_k=10),
        user_id=7,
    )

    assert retrieval_service.calls[0]["content_types"] is None
    assert [result.content_type for result in response.results] == ["code", "document"]


def test_acl_filtering_prevents_inaccessible_hits(tmp_path) -> None:
    service, retrieval_service = _build_services(
        tmp_path,
        [_document_result(), _document_result("private-doc-point")],
    )

    response = service.search(
        KnowledgeSearchRequest(query="private", mode="all", top_k=10),
        user_id=7,
    )

    assert retrieval_service.calls[0]["allowed_point_ids"] == [
        "doc-point-1",
        "code-point-1",
    ]
    assert [result.point_id for result in response.results] == ["doc-point-1"]


def test_language_source_and_top_k_filters_are_passed_to_retrieval(tmp_path) -> None:
    service, retrieval_service = _build_services(
        tmp_path,
        [_document_result(), _code_result()],
    )

    response = service.search(
        KnowledgeSearchRequest(
            query="launch",
            mode="code",
            repository_ids=[10],
            languages=["Python"],
            top_k=1,
        ),
        user_id=7,
    )

    assert retrieval_service.calls[0] == {
        "query": "launch",
        "top_k": 1,
        "allowed_point_ids": ["code-point-1"],
        "content_types": ["code"],
        "languages": ["python"],
    }
    assert [result.point_id for result in response.results] == ["code-point-1"]


def test_document_source_filter_limits_allowed_points(tmp_path) -> None:
    service, retrieval_service = _build_services(
        tmp_path,
        [_document_result(), _code_result()],
    )

    response = service.search(
        KnowledgeSearchRequest(
            query="leave",
            mode="documents",
            document_ids=[1],
            top_k=5,
        ),
        user_id=7,
    )

    assert retrieval_service.calls[0]["allowed_point_ids"] == ["doc-point-1"]
    assert [result.content_type for result in response.results] == ["document"]


def test_no_result_state_returns_empty_results(tmp_path) -> None:
    service, retrieval_service = _build_services(tmp_path, [_document_result()])

    response = service.search(
        KnowledgeSearchRequest(query="anything", mode="all", top_k=5),
        user_id=8,
    )

    assert retrieval_service.calls[0]["allowed_point_ids"] == []
    assert response.results == []
