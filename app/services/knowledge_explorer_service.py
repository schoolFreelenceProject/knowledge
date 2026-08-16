from pathlib import Path

from app.db.models import CodeSourceType
from app.schemas.documents import RetrievalResult
from app.schemas.knowledge_explorer import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    KnowledgeSourceInspection,
)
from app.services.code_metadata_service import (
    CodeMetadataPersistenceError,
    CodeMetadataService,
    CodeRepositoryMetadataNotFoundError,
    StoredCodeChunkSource,
)
from app.services.metadata_service import (
    DocumentMetadataNotFoundError,
    DocumentMetadataService,
    MetadataPersistenceError,
    StoredDocumentChunkSource,
)
from app.services.permission_service import PermissionPersistenceError, PermissionService
from app.services.retrieval_service import RetrievalService, RetrievalServiceError


class KnowledgeExplorerError(RuntimeError):
    """Raised when knowledge explorer search cannot be completed."""


class KnowledgeExplorerService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        permission_service: PermissionService,
        document_metadata_service: DocumentMetadataService,
        code_metadata_service: CodeMetadataService,
        documents_dir: str | Path,
        repositories_dir: str | Path,
        code_context_lines: int = 4,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.permission_service = permission_service
        self.document_metadata_service = document_metadata_service
        self.code_metadata_service = code_metadata_service
        self.documents_dir = Path(documents_dir)
        self.repositories_dir = Path(repositories_dir)
        self.code_context_lines = code_context_lines

    def search(
        self,
        request: KnowledgeSearchRequest,
        user_id: int,
    ) -> KnowledgeSearchResponse:
        query = request.query.strip()
        if not query:
            raise RetrievalServiceError("Query cannot be empty.")

        allowed_point_ids = self.permission_service.list_accessible_qdrant_point_ids(
            user_id
        )
        filtered_point_ids = self._apply_source_filters(
            allowed_point_ids=allowed_point_ids,
            request=request,
        )
        content_types = _content_types_for_request(request)
        languages = _languages_for_request(request)

        results = self.retrieval_service.retrieve(
            query=query,
            top_k=request.top_k,
            allowed_point_ids=filtered_point_ids,
            content_types=content_types,
            languages=languages,
        )

        return KnowledgeSearchResponse(
            query=query,
            mode=request.mode,
            top_k=request.top_k,
            retrieval_mode=str(getattr(self.retrieval_service.config, "mode", "unknown")),
            results=[
                self._to_search_result(result)
                for result in results
                if result.point_id
            ],
        )

    def _apply_source_filters(
        self,
        allowed_point_ids: list[str],
        request: KnowledgeSearchRequest,
    ) -> list[str]:
        source_point_ids: set[str] | None = None
        if request.document_ids:
            source_point_ids = set(
                self.document_metadata_service.list_chunk_point_ids(
                    document_ids=request.document_ids,
                )
            )
        if request.repository_ids:
            repository_point_ids = set(
                self.code_metadata_service.list_chunk_point_ids(
                    repository_ids=request.repository_ids,
                )
            )
            source_point_ids = (
                repository_point_ids
                if source_point_ids is None
                else source_point_ids | repository_point_ids
            )

        if source_point_ids is None:
            return allowed_point_ids

        return [
            point_id
            for point_id in allowed_point_ids
            if point_id in source_point_ids
        ]

    def _to_search_result(
        self,
        result: RetrievalResult,
    ) -> KnowledgeSearchResult:
        if not result.point_id:
            raise KnowledgeExplorerError("Retrieved result is missing a point ID.")

        if result.content_type == "code":
            return self._to_code_result(result)

        return self._to_document_result(result)

    def _to_document_result(
        self,
        result: RetrievalResult,
    ) -> KnowledgeSearchResult:
        source = self.document_metadata_service.get_document_chunk_source(
            result.point_id or ""
        )
        inspection = _document_inspection(result=result, source=source)
        return KnowledgeSearchResult(
            point_id=result.point_id or "",
            content_type="document",
            title=source.document.filename,
            score=result.score,
            vector_score=result.vector_score,
            bm25_score=result.bm25_score,
            fusion_score=result.fusion_score,
            reranker_score=result.reranker_score,
            preview=_preview_text(result.text),
            inspection=inspection,
            document_id=source.document.id,
            filename=source.document.filename,
            source_path=source.document.storage_path,
            page_number=source.chunk.page_number,
            section_heading=result.metadata.section_heading,
            heading_path=result.metadata.heading_path,
            block_kind=result.metadata.block_kind,
            workbook=result.metadata.workbook,
            sheet_name=result.metadata.sheet_name,
            cell_range=result.metadata.cell_range,
            row_start=result.metadata.row_start,
            row_end=result.metadata.row_end,
            slide_number=result.metadata.slide_number,
            slide_title=result.metadata.slide_title,
            chunk_index=source.chunk.chunk_index,
        )

    def _to_code_result(
        self,
        result: RetrievalResult,
    ) -> KnowledgeSearchResult:
        source = self.code_metadata_service.get_code_chunk_source(
            result.point_id or ""
        )
        inspection = self._code_inspection(result=result, source=source)
        return KnowledgeSearchResult(
            point_id=result.point_id or "",
            content_type="code",
            title=f"{source.repository.repo_name}/{source.file.file_path}",
            score=result.score,
            vector_score=result.vector_score,
            bm25_score=result.bm25_score,
            fusion_score=result.fusion_score,
            reranker_score=result.reranker_score,
            preview=_preview_code(result.text),
            inspection=inspection,
            chunk_index=source.chunk.chunk_index,
            repository_id=source.repository.id,
            repo_name=source.repository.repo_name,
            source_type=source.repository.source_type,
            file_path=source.file.file_path,
            language=source.file.language,
            symbol_name=source.chunk.symbol_name,
            symbol_kind=source.chunk.symbol_kind,
            start_line=source.chunk.start_line,
            end_line=source.chunk.end_line,
        )

    def _code_inspection(
        self,
        result: RetrievalResult,
        source: StoredCodeChunkSource,
    ) -> KnowledgeSourceInspection:
        file_path = self._resolve_code_file_path(source)
        if file_path is None:
            return KnowledgeSourceInspection(
                text=result.text,
                context_start_line=source.chunk.start_line,
                context_end_line=source.chunk.end_line,
                highlight_start_line=source.chunk.start_line,
                highlight_end_line=source.chunk.end_line,
            )

        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return KnowledgeSourceInspection(
                text=result.text,
                context_start_line=source.chunk.start_line,
                context_end_line=source.chunk.end_line,
                highlight_start_line=source.chunk.start_line,
                highlight_end_line=source.chunk.end_line,
            )

        if not lines:
            return KnowledgeSourceInspection(
                text=result.text,
                context_start_line=source.chunk.start_line,
                context_end_line=source.chunk.end_line,
                highlight_start_line=source.chunk.start_line,
                highlight_end_line=source.chunk.end_line,
            )

        highlight_start = max(source.chunk.start_line, 1)
        highlight_end = max(source.chunk.end_line, highlight_start)
        context_start = max(highlight_start - self.code_context_lines, 1)
        context_end = min(highlight_end + self.code_context_lines, len(lines))
        context_text = "\n".join(
            f"{line_number:>4} {lines[line_number - 1]}"
            for line_number in range(context_start, context_end + 1)
        )
        return KnowledgeSourceInspection(
            text=context_text,
            context_start_line=context_start,
            context_end_line=context_end,
            highlight_start_line=highlight_start,
            highlight_end_line=highlight_end,
        )

    def _resolve_code_file_path(
        self,
        source: StoredCodeChunkSource,
    ) -> Path | None:
        base_dir = self.repositories_dir.resolve()
        repository_path = (base_dir / source.repository.storage_path).resolve()
        try:
            repository_path.relative_to(base_dir)
        except ValueError:
            return None

        candidate = (repository_path / source.file.file_path).resolve()
        try:
            candidate.relative_to(repository_path)
        except ValueError:
            return None

        return candidate


def _content_types_for_request(
    request: KnowledgeSearchRequest,
) -> list[str] | None:
    if request.mode == "documents":
        return ["document"]
    if request.mode == "code":
        return ["code"]
    if request.content_types is None:
        return None

    normalized_content_types = [
        content_type
        for content_type in request.content_types
        if content_type in {"document", "code"}
    ]
    return normalized_content_types or []


def _languages_for_request(
    request: KnowledgeSearchRequest,
) -> list[str] | None:
    normalized_languages = [
        language.casefold()
        for language in (item.strip() for item in request.languages)
        if language
    ]
    return normalized_languages or None


def _document_inspection(
    result: RetrievalResult,
    source: StoredDocumentChunkSource,
) -> KnowledgeSourceInspection:
    return KnowledgeSourceInspection(
        text=result.text,
        context_start_line=None,
        context_end_line=None,
        highlight_start_line=None,
        highlight_end_line=None,
    )


def _preview_text(text: str, max_chars: int = 320) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized

    return f"{normalized[: max_chars - 1].rstrip()}..."


def _preview_code(text: str, max_chars: int = 420) -> str:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return normalized

    return f"{normalized[: max_chars - 1].rstrip()}..."
