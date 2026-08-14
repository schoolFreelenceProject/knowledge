from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from app.services.document_loader import (
    CorruptPdfError,
    PdfExtractionConfig,
    PdfExtractionError,
    ScannedPdfRequiresOcrError,
    load_document,
)


def test_load_text_based_pdf_extracts_text_and_page_metadata(tmp_path) -> None:
    path = tmp_path / "policy.pdf"
    _write_text_pdf(path, "Remote work policy applies to all employees.")

    documents = load_document(
        path,
        documents_dir=tmp_path,
        pdf_config=PdfExtractionConfig(min_text_chars=10, ocr_enabled=False),
    )

    assert len(documents) == 1
    assert "Remote work policy" in documents[0].text
    assert documents[0].metadata.filename == "policy.pdf"
    assert documents[0].metadata.source_path == "policy.pdf"
    assert documents[0].metadata.page_number == 1


def test_load_japanese_text_pdf_extracts_selectable_japanese_text(tmp_path) -> None:
    path = tmp_path / "japanese.pdf"
    japanese_text = "日本語能力試験N1の読解問題です。語彙と文法を確認します。"
    _write_japanese_pdf(path, japanese_text)

    documents = load_document(
        path,
        documents_dir=tmp_path,
        pdf_config=PdfExtractionConfig(min_text_chars=10, ocr_enabled=False),
    )

    assert len(documents) == 1
    assert "日本語能力試験" in documents[0].text
    assert documents[0].metadata.page_number == 1


def test_load_scanned_pdf_requires_ocr_when_ocr_is_disabled(tmp_path) -> None:
    path = tmp_path / "scanned.pdf"
    _write_image_only_pdf(path)

    with pytest.raises(ScannedPdfRequiresOcrError):
        load_document(
            path,
            documents_dir=tmp_path,
            pdf_config=PdfExtractionConfig(min_text_chars=10, ocr_enabled=False),
        )


def test_load_scanned_pdf_uses_ocr_only_for_insufficient_pages(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "scanned.pdf"
    _write_image_only_pdf(path)
    calls: list[int] = []

    def fake_ocr_pdf_page(path: Path, page_number: int, config: PdfExtractionConfig):
        calls.append(page_number)
        return "日本語 OCR テキスト 読解 文法 語彙"

    monkeypatch.setattr(
        "app.services.document_loader._ocr_pdf_page",
        fake_ocr_pdf_page,
    )

    documents = load_document(
        path,
        documents_dir=tmp_path,
        pdf_config=PdfExtractionConfig(min_text_chars=10, ocr_enabled=True),
    )

    assert calls == [1]
    assert len(documents) == 1
    assert "日本語 OCR" in documents[0].text


def test_load_scanned_pdf_reports_extraction_failed_when_ocr_has_no_text(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "qr-only.pdf"
    _write_image_only_pdf(path)

    monkeypatch.setattr(
        "app.services.document_loader._ocr_pdf_page",
        lambda path, page_number, config: "",
    )

    with pytest.raises(PdfExtractionError, match="OCR produced no usable text"):
        load_document(
            path,
            documents_dir=tmp_path,
            pdf_config=PdfExtractionConfig(min_text_chars=10, ocr_enabled=True),
        )


def test_load_corrupt_pdf_reports_corrupt_pdf(tmp_path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"this is not a pdf")

    with pytest.raises(CorruptPdfError):
        load_document(
            path,
            documents_dir=tmp_path,
            pdf_config=PdfExtractionConfig(min_text_chars=10, ocr_enabled=False),
        )


def _write_text_pdf(path: Path, text: str) -> None:
    document = canvas.Canvas(str(path), pagesize=letter)
    document.setFont("Helvetica", 12)
    document.drawString(72, 720, text)
    document.save()


def _write_japanese_pdf(path: Path, text: str) -> None:
    font_name = "HeiseiMin-W3"
    pdfmetrics.registerFont(UnicodeCIDFont(font_name))
    document = canvas.Canvas(str(path), pagesize=letter)
    document.setFont(font_name, 12)
    document.drawString(72, 720, text)
    document.save()


def _write_image_only_pdf(path: Path) -> None:
    image = Image.new("RGB", (640, 180), "white")
    draw = ImageDraw.Draw(image)
    draw.text((32, 72), "Scanned PDF page", fill="black")

    document = canvas.Canvas(str(path), pagesize=letter)
    document.drawInlineImage(image, 72, 580, width=320, height=90)
    document.save()
