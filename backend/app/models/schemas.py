from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.models.clinical import NormalizedDocument
from backend.app.models.retrieval import SearchResponse


SourceType = Literal["pdf", "text", "image", "unknown"]
RecordStatus = Literal["uploaded", "extracted", "failed"]


class RecordSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    source_type: SourceType
    mime_type: str | None = None
    size_bytes: int
    status: RecordStatus
    created_at: datetime
    extracted_characters: int = 0
    owner_id: str | None = None
    patient_id: str | None = None


class RecordDetail(RecordSummary):
    text: str | None = None
    error: str | None = None
    structured: NormalizedDocument | None = None


class RecordListResponse(BaseModel):
    items: list[RecordSummary]
    total: int


class HealthResponse(BaseModel):
    status: str
    app: str
    env: str
    phase: str


__all__ = ["HealthResponse", "RecordDetail", "RecordListResponse", "RecordSummary", "SearchResponse"]
