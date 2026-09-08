from datetime import datetime, timezone

from backend.app.models.clinical import NormalizedDocument, Observation
from backend.app.models.schemas import RecordSummary
from backend.app.services.timeline import TimelineService


class FakeRecords:
    def list_records(self):
        return [RecordSummary(id="a" * 32, filename="lab.txt", source_type="text", size_bytes=1, status="extracted", created_at=datetime.now(timezone.utc))]

    def get_record(self, record_id):
        from types import SimpleNamespace

        return SimpleNamespace(
            structured=NormalizedDocument(
                record_id=record_id,
                document_type="lab_report",
                document_date="2026-01-14",
                observations=[Observation(name="glucose", value="100", unit="mg/dL", source_text="glucose 100 mg/dL")],
            )
        )


def test_timeline_is_built_from_normalized_documents():
    response = TimelineService(FakeRecords()).build()

    assert response.events[0].event_date.isoformat() == "2026-01-14"
    assert response.events[0].observations[0].name == "glucose"
