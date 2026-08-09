from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, CodeChunkRecord, CodeFileRecord, CodeRepositoryRecord
from app.schemas.documents import ChunkMetadata, DocumentChunk
from app.services.code_metadata_service import CodeMetadataService
from app.services.code_parser import ParsedCodeFile
from app.services.vector_store import StoredVectorBatch


def _build_service():
    engine = create_engine("sqlite:///:memory:")
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = CodeMetadataService(
        session_factory=session_factory,
        init_database=lambda: Base.metadata.create_all(bind=engine),
    )
    return service, session_factory


def _parsed_file() -> ParsedCodeFile:
    return ParsedCodeFile(
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
        file_path="app.py",
        language="python",
        text="def hello():\n    return 'hi'\n",
        file_hash="b" * 64,
        size_bytes=29,
        source_path="repo@aaaaaaaa/app.py",
        symbols=[],
    )


def _chunk() -> DocumentChunk:
    return DocumentChunk(
        text="def hello():\n    return 'hi'",
        metadata=ChunkMetadata(
            filename="app.py",
            source_path="repo@aaaaaaaa/app.py",
            file_type="code",
            content_type="code",
            page_number=None,
            chunk_index=1,
            start_char=0,
            end_char=28,
            repo_name="repo",
            repo_url="file:///repo",
            branch="main",
            commit_sha="a" * 40,
            language="python",
            symbol_name="hello",
            symbol_kind="function",
            start_line=1,
            end_line=2,
            repository_file_path="app.py",
        ),
    )


def test_code_metadata_persistence_creates_repository_files_and_chunks() -> None:
    service, session_factory = _build_service()

    persisted = service.save_repository_metadata(
        parsed_files=[_parsed_file()],
        chunks=[_chunk()],
        stored_batch=StoredVectorBatch(
            collection_name="company_documents",
            stored_count=1,
            vector_size=3,
            point_ids=["code-point-1"],
        ),
        repo_url="file:///repo",
        repo_name="repo",
        branch="main",
        commit_sha="a" * 40,
        storage_path="repo/main/aaaaaaaa",
    )

    with session_factory() as session:
        repository = session.scalars(select(CodeRepositoryRecord)).one()
        code_file = session.scalars(select(CodeFileRecord)).one()
        code_chunk = session.scalars(select(CodeChunkRecord)).one()

    assert persisted.repository_id == repository.id
    assert persisted.saved_files == 1
    assert persisted.saved_chunks == 1
    assert repository.status == "INDEXED"
    assert code_file.repository_id == repository.id
    assert code_file.file_path == "app.py"
    assert code_chunk.repository_id == repository.id
    assert code_chunk.code_file_id == code_file.id
    assert code_chunk.qdrant_point_id == "code-point-1"
    assert code_chunk.symbol_name == "hello"
