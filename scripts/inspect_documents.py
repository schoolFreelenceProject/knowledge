import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.document_loader import DocumentLoaderError, load_documents


DEFAULT_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect extracted text from PDF and Markdown documents."
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DEFAULT_DOCUMENTS_DIR,
        help="Directory containing PDF and Markdown files.",
    )
    parser.add_argument(
        "--format",
        choices=("preview", "json"),
        default="preview",
        help="Output format.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=800,
        help="Maximum preview characters per extracted document block.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        extracted_documents = load_documents(args.documents_dir)
    except (DocumentLoaderError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        payload = [document.model_dump(mode="json") for document in extracted_documents]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Documents directory: {args.documents_dir}")
    print(f"Extracted blocks: {len(extracted_documents)}")

    if not extracted_documents:
        print("No supported PDF or Markdown documents found.")
        return 0

    for index, document in enumerate(extracted_documents, start=1):
        metadata = document.metadata
        page_label = (
            f"page {metadata.page_number}"
            if metadata.page_number is not None
            else "document"
        )
        preview = _preview_text(document.text, max_chars=args.max_chars)

        print()
        print(f"[{index}] {metadata.filename} ({metadata.file_type}, {page_label})")
        print(f"source: {metadata.source_path}")
        print(f"characters: {len(document.text)}")
        print(preview)

    return 0


def _preview_text(text: str, max_chars: int) -> str:
    if not text:
        return "<no extractable text>"

    if max_chars < 1:
        return ""

    if len(text) <= max_chars:
        return text

    return f"{text[:max_chars].rstrip()}\n..."


if __name__ == "__main__":
    raise SystemExit(main())
