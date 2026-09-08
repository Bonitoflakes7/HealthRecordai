import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.app.core.config import settings
from backend.app.models.schemas import RecordDetail, RecordSummary, SourceType
from backend.app.models.clinical import NormalizedDocument


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

    async def save_upload(self, upload: UploadFile, owner_id: str = "dev-user") -> RecordSummary:
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

        now = datetime.now(timezone.utc)
        manifest = RecordSummary(
            id=record_id,
            filename=filename,
            source_type=self._source_type(upload.content_type, filename),
            mime_type=upload.content_type,
            size_bytes=size,
            status="uploaded",
            created_at=now,
            owner_id=owner_id,
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
        (self._record_dir(record_id) / "structured.json").write_text(document.model_dump_json(indent=2), encoding="utf-8")
        return record.model_copy(update={"structured": document})

    def _record_dir(self, record_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", record_id):
            raise ValueError("invalid record id")
        return self.store_path / record_id

    @staticmethod
    def _safe_filename(filename: str) -> str:
        return Path(filename).name.replace("\x00", "_") or "unnamed-record"

    @staticmethod
    def _source_type(mime_type: str | None, filename: str) -> SourceType:
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            return "pdf"
        if mime_type and mime_type.startswith("text/"):
            return "text"
        if mime_type and mime_type.startswith("image/"):
            return "image"
        return "unknown"

    @staticmethod
    def _read_manifest(path: Path) -> RecordSummary:
        return RecordSummary(**json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def _write_manifest(record_dir: Path, manifest: RecordSummary) -> None:
        (record_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
