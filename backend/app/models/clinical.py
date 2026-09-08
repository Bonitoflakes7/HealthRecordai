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


class Condition(BaseModel):
    name: str
    status: str = "documented"
    source_text: str


class Medication(BaseModel):
    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    indication: str | None = None
    action: str = "documented"
    status: str = "unknown"
    source_text: str


class Investigation(BaseModel):
    name: str
    status: str = "documented"
    result: str | None = None
    source_text: str


class Procedure(BaseModel):
    name: str
    status: str = "documented"
    source_text: str


class NormalizedDocument(BaseModel):
    record_id: str
    document_type: DocumentType = "unknown"
    title: str | None = None
    document_date: date | None = None
    sections: list[DocumentSection] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    investigations: list[Investigation] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)
