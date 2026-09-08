import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from backend.app.core.config import settings
from backend.app.models.schemas import SourceType


class ExtractionError(RuntimeError):
    """Raised when a document cannot be converted into text."""


class ExtractedPages:
    def __init__(self, pages: list[str]) -> None:
        self.pages = pages

    @property
    def text(self) -> str:
        return "\n\n".join(page for page in self.pages if page).strip()


class DocumentExtractor:
    def __init__(self, pdftoppm_cmd: str | None = None, tesseract_cmd: str | None = None) -> None:
        self.pdftoppm_cmd = pdftoppm_cmd or settings.pdftoppm_cmd
        self.tesseract_cmd = tesseract_cmd or settings.tesseract_cmd

    def extract(self, path: Path, source_type: SourceType) -> str:
        return self.extract_with_pages(path, source_type).text

    def extract_with_pages(self, path: Path, source_type: SourceType) -> ExtractedPages:
        if source_type == "pdf":
            return ExtractedPages(self._extract_pdf_pages(path))
        if source_type == "image":
            return ExtractedPages([self._ocr_image(path)])
        if source_type == "text":
            return ExtractedPages([path.read_text(encoding="utf-8")])
        raise ExtractionError("unsupported document type")

    def _extract_pdf(self, path: Path) -> str:
        return ExtractedPages(self._extract_pdf_pages(path)).text

    def _extract_pdf_pages(self, path: Path) -> list[str]:
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:  # pypdf exposes several parser-specific exceptions.
            raise ExtractionError(f"could not read PDF: {exc}") from exc

        if any(page.strip() for page in pages):
            return pages
        return self._ocr_pdf(path)

    def _ocr_pdf(self, path: Path) -> list[str]:
        if not shutil.which(self.pdftoppm_cmd):
            raise ExtractionError("PDF has no embedded text and pdftoppm is not installed")
        with tempfile.TemporaryDirectory(prefix="health-record-ocr-") as temp_dir:
            prefix = Path(temp_dir) / "page"
            self._run([self.pdftoppm_cmd, "-png", "-r", "200", str(path), str(prefix)])
            image_pages = sorted(Path(temp_dir).glob("page-*.png"))
            if not image_pages:
                raise ExtractionError("PDF rendered no pages for OCR")
            return [self._ocr_image(page) for page in image_pages]

    def _ocr_image(self, path: Path) -> str:
        if not shutil.which(self.tesseract_cmd):
            raise ExtractionError("tesseract is not installed")
        result = self._run([self.tesseract_cmd, str(path), "stdout", "-l", "eng"])
        text = result.stdout.strip()
        if not text:
            raise ExtractionError("OCR produced no text")
        return text

    @staticmethod
    def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise ExtractionError(f"required executable is not installed: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "command failed").strip()
            raise ExtractionError(f"{command[0]} failed: {detail}") from exc
