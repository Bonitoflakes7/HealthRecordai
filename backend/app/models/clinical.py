from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


DocumentType = Literal[
    "lab_report",
    "prescription",
    "discharge_summary",
    "imaging_report",
    "clinical_note",
    "unknown",
]


class DocumentSection(BaseModel):
    heading: str
    text: str


class Observation(BaseModel):
    name: str
    value: str
    unit: str | None = None
    observed_on: date | None = None
    source_text: str


class NormalizedDocument(BaseModel):
    record_id: str
    document_type: DocumentType = "unknown"
    title: str | None = None
    document_date: date | None = None
    sections: list[DocumentSection] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
