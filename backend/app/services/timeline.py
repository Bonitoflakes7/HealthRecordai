from datetime import date

from backend.app.models.timeline import TimelineEvent, TimelineResponse
from backend.app.services.records import RecordStore


class TimelineService:
    def __init__(self, records: RecordStore) -> None:
        self.records = records

    def build(self, limit: int = 100, owner_id: str | None = None) -> TimelineResponse:
        events: list[TimelineEvent] = []
        summaries = self.records.list_records(owner_id) if owner_id is not None else self.records.list_records()
        for summary in summaries:
            detail = self.records.get_record(summary.id, owner_id) if owner_id is not None else self.records.get_record(summary.id)
            if not detail or not detail.structured:
                continue
            document = detail.structured
            events.append(
                TimelineEvent(
                    event_date=document.document_date,
                    record_id=summary.id,
                    filename=summary.filename,
                    document_type=document.document_type,
                    title=document.title,
                    date_candidates=document.date_candidates,
                    observations=document.observations,
                    conditions=document.conditions,
                    medications=document.medications,
                    investigations=document.investigations,
                    procedures=document.procedures,
                    clinical_events=document.clinical_events,
                )
            )
        events.sort(key=lambda event: event.event_date or date.min, reverse=True)
        return TimelineResponse(events=events[: max(1, min(limit, 500))])
