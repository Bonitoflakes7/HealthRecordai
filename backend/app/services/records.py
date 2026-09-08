import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from pypdf import PdfReader

from backend.app.core.config import settings
from backend.app.models.schemas import RecordDetail, RecordSummary, SourceType
from backend.app.models.clinical import NormalizedDocument


class UploadValidationError(ValueError):
    """Raised when an upload fails byte-level validation."""


class RecordStore:
    def __init__(self, root: Path | None = None) -> None:
        self.store_path = (root or settings.data_dir / "records").resolve()
        self.store_path.mkdir(parents=True, exist_ok=True)

    def list_records(self, owner_id: str | None = None) -> list[RecordSummary]:
        records = [self._read_manifest(path) for path in self.store_path.glob("*/manifest.json")]
        if owner_id is not None:
            records = [record for record in records if record.owner_id == owner_id]
        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def get_record(self, record_id: str, owner_id: str | None = None) -> RecordDetail | None:
        record_dir = self._record_dir(record_id)
        manifest_path = record_dir / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = self._read_manifest(manifest_path)
        if owner_id is not None and manifest.owner_id != owner_id:
            return None
        text_path = record_dir / "extracted.txt"
        error_path = record_dir / "error.txt"
        structured_path = record_dir / "structured.json"
        return RecordDetail(
            **manifest.model_dump(),
            text=text_path.read_text(encoding="utf-8") if text_path.exists() else None,
            error=error_path.read_text(encoding="utf-8") if error_path.exists() else None,
            structured=NormalizedDocument(**json.loads(structured_path.read_text(encoding="utf-8"))) if structured_path.exists() else None,
        )

    def raw_path(self, record_id: str) -> Path:
        record_dir = self._record_dir(record_id)
        manifest = self._read_manifest(record_dir / "manifest.json")
        return record_dir / manifest.filename

    async def save_upload(self, upload: UploadFile, owner_id: str = "dev-user", patient_id: str | None = None) -> RecordSummary:
        record_id = uuid4().hex
        record_dir = self._record_dir(record_id)
        record_dir.mkdir(parents=True)
        filename = self._safe_filename(upload.filename or "unnamed-record")
        raw_path = record_dir / filename
        size = 0
        with raw_path.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raw_path.unlink(missing_ok=True)
                    record_dir.rmdir()
                    raise ValueError(f"file exceeds {settings.max_upload_mb} MB limit")
                output.write(chunk)

        try:
            source_type = self._validate_upload(raw_path, filename, upload.content_type, size)
        except UploadValidationError:
            raw_path.unlink(missing_ok=True)
            record_dir.rmdir()
            raise

        now = datetime.now(timezone.utc)
        manifest = RecordSummary(
            id=record_id,
            filename=filename,
            source_type=source_type,
            mime_type=upload.content_type,
            size_bytes=size,
            status="uploaded",
            created_at=now,
            owner_id=owner_id,
            patient_id=self._validate_patient_id(patient_id),
        )
        self._write_manifest(record_dir, manifest)
        return manifest

    def set_extracted(self, record_id: str, text: str) -> RecordDetail:
        record_dir = self._record_dir(record_id)
        manifest = self._read_manifest(record_dir / "manifest.json").model_copy(
            update={"status": "extracted", "extracted_characters": len(text)}
        )
        (record_dir / "extracted.txt").write_text(text, encoding="utf-8")
        (record_dir / "error.txt").unlink(missing_ok=True)
        self._write_manifest(record_dir, manifest)
        return RecordDetail(**manifest.model_dump(), text=text)

    def set_failed(self, record_id: str, error: str) -> RecordDetail:
        record_dir = self._record_dir(record_id)
        manifest = self._read_manifest(record_dir / "manifest.json").model_copy(update={"status": "failed"})
        (record_dir / "error.txt").write_text(error, encoding="utf-8")
        self._write_manifest(record_dir, manifest)
        return RecordDetail(**manifest.model_dump(), error=error)

    def set_structured(self, record_id: str, document: NormalizedDocument, owner_id: str | None = None) -> RecordDetail:
        record = self.get_record(record_id, owner_id)
        if record is None:
            raise ValueError("record not found")
        patient_id = document.patient_id or record.patient_id
        if patient_id != document.patient_id:
            document = document.model_copy(update={"patient_id": patient_id})
        (self._record_dir(record_id) / "structured.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
        manifest = self._read_manifest(self._record_dir(record_id) / "manifest.json").model_copy(update={"patient_id": patient_id})
        self._write_manifest(self._record_dir(record_id), manifest)
        return record.model_copy(update={"structured": document, "patient_id": patient_id})

    def _record_dir(self, record_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", record_id):
            raise ValueError("invalid record id")
        return self.store_path / record_id

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return Path(filename).name.replace("\x00", "_") or "unnamed-record"

    @staticmethod
    def _validate_patient_id(patient_id: str | None) -> str | None:
        if patient_id is None or not patient_id.strip():
            return None
        value = patient_id.strip()
        if len(value) > 128 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value):
            raise UploadValidationError("patient_id must be 1-128 characters using letters, numbers, dots, underscores, slashes, or hyphens")
        return value

    @staticmethod
    def _validate_upload(path: Path, filename: str, mime_type: str | None, size: int) -> SourceType:
        if size == 0:
            raise UploadValidationError("empty files are not allowed")
        extension = Path(filename).suffix.casefold()
        allowed = {".pdf": "pdf", ".txt": "text", ".md": "text", ".csv": "text", ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image"}
        source_type = allowed.get(extension)
        if source_type is None:
            raise UploadValidationError("unsupported file type; upload a PDF, text file, or PNG/JPEG/WEBP image")
        declared = (mime_type or "").casefold()
        if source_type == "pdf":
            signature = path.read_bytes()[:5]
            if signature != b"%PDF-":
                raise UploadValidationError("file extension is .pdf but the file signature is not a PDF")
            try:
                if not PdfReader(str(path)).pages:
                    raise UploadValidationError("PDF contains no readable pages")
            except UploadValidationError:
                raise
            except Exception as exc:
                raise UploadValidationError("PDF structure could not be validated") from exc
            if declared and declared not in {"application/pdf", "application/octet-stream"}:
                raise UploadValidationError("PDF extension and declared content type do not match")
        elif source_type == "image":
            signature = path.read_bytes()[:12]
            signatures = {
                ".png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
                ".jpg": signature.startswith(b"\xff\xd8\xff"),
                ".jpeg": signature.startswith(b"\xff\xd8\xff"),
                ".webp": signature.startswith(b"RIFF") and signature[8:12] == b"WEBP",
            }
            if not signatures[extension]:
                raise UploadValidationError("image extension does not match the file signature")
            if declared and (not declared.startswith("image/") or (extension == ".png" and declared != "image/png") or (extension in {".jpg", ".jpeg"} and declared not in {"image/jpeg", "image/jpg"}) or (extension == ".webp" and declared != "image/webp")):
                raise UploadValidationError("image extension and declared content type do not match")
        else:
            if declared and not (declared.startswith("text/") or declared == "application/octet-stream"):
                raise UploadValidationError("text extension and declared content type do not match")
            try:
                content = path.read_bytes()
                content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise UploadValidationError("text files must be valid UTF-8") from exc
            if b"\x00" in content:
                raise UploadValidationError("binary content is not allowed in text uploads")
        return source_type

    @staticmethod
    def _read_manifest(path: Path) -> RecordSummary:
        return RecordSummary(**json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _write_manifest(record_dir: Path, manifest: RecordSummary) -> None:
        (record_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
