import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.schemas.documents import DocumentFileType, DocumentMetadata, ExtractedDocument


PDF_EXTENSION = ".pdf"
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
SUPPORTED_EXTENSIONS = {PDF_EXTENSION, *MARKDOWN_EXTENSIONS}
DEFAULT_PDF_MIN_TEXT_CHARS = 20
DEFAULT_PDF_OCR_DPI = 200
DEFAULT_PDF_OCR_LANGUAGES = "jpn+eng"
DEFAULT_PDF_OCR_TIMEOUT_SECONDS = 120
DEFAULT_PDF_OCR_MAX_PAGES = 100
DEFAULT_PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class PdfExtractionConfig:
    min_text_chars: int = DEFAULT_PDF_MIN_TEXT_CHARS
    ocr_enabled: bool = False
    ocr_languages: str = DEFAULT_PDF_OCR_LANGUAGES
    ocr_dpi: int = DEFAULT_PDF_OCR_DPI
    ocr_timeout_seconds: int = DEFAULT_PDF_OCR_TIMEOUT_SECONDS
    ocr_max_pages: int = DEFAULT_PDF_OCR_MAX_PAGES
    text_extraction_timeout_seconds: int = (
        DEFAULT_PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS
    )


class DocumentLoaderError(RuntimeError):
    """Raised when a document cannot be loaded or parsed."""


class UnsupportedDocumentTypeError(DocumentLoaderError):
    """Raised when a file extension is not supported by the MVP parser."""


class PdfExtractionError(DocumentLoaderError):
    """Raised when PDF text cannot be extracted into usable content."""


class ScannedPdfRequiresOcrError(PdfExtractionError):
    """Raised when a PDF appears image-only and OCR is disabled or unavailable."""


class EncryptedPdfError(PdfExtractionError):
    """Raised when a PDF is encrypted and cannot be read without a password."""


class CorruptPdfError(PdfExtractionError):
    """Raised when a PDF cannot be parsed as a supported PDF file."""


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
    pdf_config: PdfExtractionConfig | None = None,
) -> list[ExtractedDocument]:
    path = Path(document_path)
    if not path.exists():
        raise FileNotFoundError(f"Document does not exist: {path}")
    if not path.is_file():
        raise DocumentLoaderError(f"Document path is not a file: {path}")

    base_dir = Path(documents_dir) if documents_dir is not None else path.parent
    extension = path.suffix.lower()

    if extension == PDF_EXTENSION:
        return _load_pdf(path, base_dir=base_dir, config=_resolve_pdf_config(pdf_config))
    if extension in MARKDOWN_EXTENSIONS:
        return [_load_markdown(path, base_dir=base_dir)]

    raise UnsupportedDocumentTypeError(
        f"Unsupported document type '{extension}'. "
        f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def _load_pdf(
    path: Path,
    base_dir: Path,
    config: PdfExtractionConfig,
) -> list[ExtractedDocument]:
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
        raise CorruptPdfError(f"Failed to read PDF '{path}'.") from exc

    if reader.is_encrypted and not _decrypt_pdf_without_password(reader):
        raise EncryptedPdfError(f"PDF '{path}' is encrypted.")

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise CorruptPdfError(f"Failed to inspect PDF pages for '{path}'.") from exc

    page_texts: list[str] = []
    for page in reader.pages:
        try:
            page_texts.append(_normalize_text(page.extract_text() or ""))
        except Exception:
            page_texts.append("")

    _fill_insufficient_pages_with_poppler_text(path=path, page_texts=page_texts, config=config)
    insufficient_page_indexes = _insufficient_page_indexes(page_texts, config)
    if insufficient_page_indexes:
        if config.ocr_enabled:
            if len(insufficient_page_indexes) > config.ocr_max_pages:
                raise ScannedPdfRequiresOcrError(
                    "PDF requires OCR for too many pages. "
                    f"Maximum OCR page count is {config.ocr_max_pages}."
                )
            _fill_insufficient_pages_with_ocr(
                path=path,
                page_texts=page_texts,
                page_indexes=insufficient_page_indexes,
                config=config,
            )
        elif _has_no_usable_text(page_texts, config):
            raise ScannedPdfRequiresOcrError(
                "PDF appears to be scanned or image-only and requires OCR."
            )

    extracted_pages: list[ExtractedDocument] = []
    for page_index, text in enumerate(page_texts, start=1):
        if _meaningful_text_length(text) < config.min_text_chars:
            continue
        metadata = _build_metadata(
            path=path,
            base_dir=base_dir,
            file_type="pdf",
            page_number=page_index,
        )
        extracted_pages.append(ExtractedDocument(text=text, metadata=metadata))

    if not extracted_pages:
        if _pdf_has_images(path):
            if config.ocr_enabled:
                raise PdfExtractionError("PDF OCR produced no usable text.")
            raise ScannedPdfRequiresOcrError(
                "PDF appears to be scanned or image-only and requires OCR."
            )
        raise PdfExtractionError("PDF text extraction produced no usable text.")

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
    source_path = _relative_source_path(path=path, base_dir=base_dir)
    return DocumentMetadata(
        filename=source_path if "/" in source_path else path.name,
        source_path=source_path,
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
    return text.replace("\x0c", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()


def _resolve_pdf_config(
    config: PdfExtractionConfig | None,
) -> PdfExtractionConfig:
    return config or PdfExtractionConfig()


def _decrypt_pdf_without_password(reader) -> bool:
    try:
        return bool(reader.decrypt(""))
    except Exception:
        return False


def _fill_insufficient_pages_with_poppler_text(
    path: Path,
    page_texts: list[str],
    config: PdfExtractionConfig,
) -> None:
    for page_index in _insufficient_page_indexes(page_texts, config):
        poppler_text = _extract_pdf_page_text_with_poppler(
            path=path,
            page_number=page_index + 1,
            timeout_seconds=config.text_extraction_timeout_seconds,
        )
        if poppler_text is None:
            continue
        if _meaningful_text_length(poppler_text) > _meaningful_text_length(
            page_texts[page_index]
        ):
            page_texts[page_index] = poppler_text


def _fill_insufficient_pages_with_ocr(
    path: Path,
    page_texts: list[str],
    page_indexes: list[int],
    config: PdfExtractionConfig,
) -> None:
    for page_index in page_indexes:
        ocr_text = _ocr_pdf_page(
            path=path,
            page_number=page_index + 1,
            config=config,
        )
        if _meaningful_text_length(ocr_text) > _meaningful_text_length(
            page_texts[page_index]
        ):
            page_texts[page_index] = ocr_text


def _extract_pdf_page_text_with_poppler(
    path: Path,
    page_number: int,
    timeout_seconds: int,
) -> str | None:
    if shutil.which("pdftotext") is None:
        return None

    try:
        completed = subprocess.run(
            [
                "pdftotext",
                "-layout",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                str(path),
                "-",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None

    return _normalize_text(completed.stdout)


def _ocr_pdf_page(
    path: Path,
    page_number: int,
    config: PdfExtractionConfig,
) -> str:
    if shutil.which("pdftoppm") is None or shutil.which("tesseract") is None:
        raise ScannedPdfRequiresOcrError(
            "PDF appears to be scanned or image-only and OCR tools are unavailable."
        )

    with tempfile.TemporaryDirectory(prefix="pdf-ocr-") as temp_dir:
        image_prefix = Path(temp_dir) / "page"
        try:
            render = subprocess.run(
                [
                    "pdftoppm",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-r",
                    str(config.ocr_dpi),
                    "-png",
                    str(path),
                    str(image_prefix),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.ocr_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfExtractionError("PDF page rendering timed out for OCR.") from exc
        if render.returncode != 0:
            raise PdfExtractionError("PDF page could not be rendered for OCR.")

        image_paths = sorted(Path(temp_dir).glob("page-*.png"))
        if not image_paths:
            raise PdfExtractionError("PDF page rendering produced no OCR image.")

        try:
            ocr = subprocess.run(
                [
                    "tesseract",
                    str(image_paths[0]),
                    "stdout",
                    "-l",
                    config.ocr_languages,
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.ocr_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfExtractionError("PDF OCR timed out.") from exc
        if ocr.returncode != 0:
            if (
                "Error opening data file" in ocr.stderr
                or "Failed loading language" in ocr.stderr
            ):
                raise ScannedPdfRequiresOcrError(
                    "PDF appears to be scanned or image-only and OCR language data is unavailable."
                )
            raise PdfExtractionError("PDF OCR failed.")

        return _normalize_text(ocr.stdout)


def _insufficient_page_indexes(
    page_texts: list[str],
    config: PdfExtractionConfig,
) -> list[int]:
    return [
        index
        for index, text in enumerate(page_texts)
        if _meaningful_text_length(text) < config.min_text_chars
    ]


def _has_no_usable_text(
    page_texts: list[str],
    config: PdfExtractionConfig,
) -> bool:
    return all(
        _meaningful_text_length(text) < config.min_text_chars
        for text in page_texts
    )


def _meaningful_text_length(text: str) -> int:
    return sum(1 for character in text if character.isalnum())


def _pdf_has_images(path: Path) -> bool:
    if shutil.which("pdfimages") is None:
        return False

    try:
        completed = subprocess.run(
            ["pdfimages", "-list", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DEFAULT_PDF_TEXT_EXTRACTION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    if completed.returncode != 0:
        return False

    return len(completed.stdout.splitlines()) > 2
