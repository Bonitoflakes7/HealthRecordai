from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class TrendPoint(BaseModel):
    observed_on: date | None = None
    value: float
    unit: str | None = None
    record_id: str
    citation_id: str


class MetricTrend(BaseModel):
    metric: str
    direction: Literal["increasing", "decreasing", "stable", "insufficient_data"]
    points: list[TrendPoint] = Field(default_factory=list)
    latest_value: float | None = None
    change: float | None = None


class RiskSignal(BaseModel):
    code: str
    severity: Literal["review", "urgent_review"]
    metric: str
    title: str
    detail: str
    observed_on: date | None = None
    record_id: str
    citation_id: str
    source_reference: str | None = None


class AnalyticsResponse(BaseModel):
    trends: list[MetricTrend] = Field(default_factory=list)
    signals: list[RiskSignal] = Field(default_factory=list)
