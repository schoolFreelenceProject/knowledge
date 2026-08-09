from pathlib import Path

from app.schemas.documents import DocumentFileType, DocumentMetadata, ExtractedDocument


PDF_EXTENSION = ".pdf"
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
SUPPORTED_EXTENSIONS = {PDF_EXTENSION, *MARKDOWN_EXTENSIONS}


class DocumentLoaderError(RuntimeError):
    """Raised when a document cannot be loaded or parsed."""


class UnsupportedDocumentTypeError(DocumentLoaderError):
    """Raised when a file extension is not supported by the MVP parser."""


def discover_document_paths(documents_dir: str | Path) -> list[Path]:
    root = Path(documents_dir)
    if not root.exists():
        raise FileNotFoundError(f"Documents directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Documents path is not a directory: {root}")

    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def load_documents(documents_dir: str | Path) -> list[ExtractedDocument]:
    root = Path(documents_dir)
    extracted_documents: list[ExtractedDocument] = []

    for document_path in discover_document_paths(root):
        extracted_documents.extend(load_document(document_path, documents_dir=root))

    return extracted_documents


def load_document(
    document_path: str | Path,
    documents_dir: str | Path | None = None,
) -> list[ExtractedDocument]:
    path = Path(document_path)
    if not path.exists():
        raise FileNotFoundError(f"Document does not exist: {path}")
    if not path.is_file():
        raise DocumentLoaderError(f"Document path is not a file: {path}")

    base_dir = Path(documents_dir) if documents_dir is not None else path.parent
    extension = path.suffix.lower()

    if extension == PDF_EXTENSION:
        return _load_pdf(path, base_dir=base_dir)
    if extension in MARKDOWN_EXTENSIONS:
        return [_load_markdown(path, base_dir=base_dir)]

    raise UnsupportedDocumentTypeError(
        f"Unsupported document type '{extension}'. "
        f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def _load_pdf(path: Path, base_dir: Path) -> list[ExtractedDocument]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentLoaderError(
            "PDF parsing requires pypdf. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf exposes multiple parse-time exceptions.
        raise DocumentLoaderError(f"Failed to read PDF '{path}': {exc}") from exc

    extracted_pages: list[ExtractedDocument] = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = _normalize_text(page.extract_text() or "")
        metadata = _build_metadata(
            path=path,
            base_dir=base_dir,
            file_type="pdf",
            page_number=page_index,
        )
        extracted_pages.append(ExtractedDocument(text=text, metadata=metadata))

    return extracted_pages


def _load_markdown(path: Path, base_dir: Path) -> ExtractedDocument:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentLoaderError(
            f"Failed to read Markdown file '{path}' as UTF-8 text."
        ) from exc

    metadata = _build_metadata(
        path=path,
        base_dir=base_dir,
        file_type="markdown",
        page_number=None,
    )
    return ExtractedDocument(text=_normalize_text(text), metadata=metadata)


def _build_metadata(
    path: Path,
    base_dir: Path,
    file_type: DocumentFileType,
    page_number: int | None,
) -> DocumentMetadata:
    return DocumentMetadata(
        filename=path.name,
        source_path=_relative_source_path(path=path, base_dir=base_dir),
        file_type=file_type,
        page_number=page_number,
    )


def _relative_source_path(path: Path, base_dir: Path) -> str:
    resolved_path = path.resolve()
    resolved_base_dir = base_dir.resolve()

    try:
        return resolved_path.relative_to(resolved_base_dir).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()
