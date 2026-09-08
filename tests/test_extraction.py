from pathlib import Path

import pytest

from backend.app.services import extraction
from backend.app.services.extraction import DocumentExtractor, ExtractionError


def test_text_extraction_reads_utf8(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("Medication started", encoding="utf-8")

    assert DocumentExtractor().extract(source, "text") == "Medication started"


def test_pdf_embedded_text_is_used_without_ocr(monkeypatch, tmp_path: Path):
    class FakePage:
        def extract_text(self):
            return "Report date: 2026-01-01"

    class FakeReader:
        pages = [FakePage()]

    monkeypatch.setattr(extraction, "PdfReader", lambda _: FakeReader())
    monkeypatch.setattr(extraction.shutil, "which", lambda _: None)

    assert DocumentExtractor().extract(tmp_path / "report.pdf", "pdf") == "Report date: 2026-01-01"


def test_pdf_page_extraction_preserves_page_boundaries(monkeypatch, tmp_path: Path):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        pages = [FakePage("Page one"), FakePage("Page two")]

    monkeypatch.setattr(extraction, "PdfReader", lambda _: FakeReader())
    result = DocumentExtractor().extract_with_pages(tmp_path / "report.pdf", "pdf")

    assert result.pages == ["Page one", "Page two"]
    assert result.text == "Page one\n\nPage two"


def test_image_extraction_reports_missing_tesseract(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(extraction.shutil, "which", lambda _: None)

    with pytest.raises(ExtractionError, match="tesseract is not installed"):
        DocumentExtractor().extract(tmp_path / "scan.png", "image")


def test_unknown_source_type_is_rejected(tmp_path: Path):
    with pytest.raises(ExtractionError, match="unsupported document type"):
        DocumentExtractor().extract(tmp_path / "record.bin", "unknown")
