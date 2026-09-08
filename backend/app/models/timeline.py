from datetime import date

from pydantic import BaseModel, Field

from backend.app.models.clinical import Condition, Investigation, Medication, Observation, Procedure


class TimelineEvent(BaseModel):
    event_date: date | None = None
    record_id: str
    filename: str
    document_type: str
    title: str | None = None
    observations: list[Observation] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    investigations: list[Investigation] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    events: list[TimelineEvent] = Field(default_factory=list)
