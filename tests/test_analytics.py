from datetime import date
from types import SimpleNamespace

from backend.app.models.clinical import NormalizedDocument, Observation
from backend.app.models.schemas import RecordSummary
from backend.app.services.analytics import ClinicalAnalyticsService


class FakeRecords:
    def list_records(self):
        return [
            RecordSummary(id="a" * 32, filename="one.txt", source_type="text", size_bytes=1, status="extracted", created_at="2026-01-01T00:00:00Z"),
            RecordSummary(id="b" * 32, filename="two.txt", source_type="text", size_bytes=1, status="extracted", created_at="2026-01-02T00:00:00Z"),
        ]

    def get_record(self, record_id):
        value = "120/80" if record_id.startswith("a") else "140/90"
        observed = date(2026, 1, 1) if record_id.startswith("a") else date(2026, 2, 1)
        return SimpleNamespace(
            structured=NormalizedDocument(
                record_id=record_id,
                document_type="lab_report",
                document_date=observed,
                observations=[Observation(name="blood_pressure", value=value, unit="mmHg", observed_on=observed, source_text=value)],
            )
        )


def test_analytics_builds_ordered_blood_pressure_trends():
    response = ClinicalAnalyticsService(FakeRecords()).analyze()

    systolic = next(item for item in response.trends if item.metric == "blood_pressure_systolic")
    assert systolic.direction == "increasing"
    assert systolic.points[0].value == 120
    assert systolic.points[-1].value == 140
    assert response.signals == []


def test_analytics_emits_cited_severe_pressure_signal():
    class OneRecord(FakeRecords):
        def list_records(self):
            return [RecordSummary(id="c" * 32, filename="urgent.txt", source_type="text", size_bytes=1, status="extracted", created_at="2026-01-01T00:00:00Z")]

        def get_record(self, record_id):
            return SimpleNamespace(
                structured=NormalizedDocument(
                    record_id=record_id,
                    document_type="clinical_note",
                    document_date=date(2026, 1, 1),
                    observations=[Observation(name="blood_pressure", value="190/121", unit="mmHg", source_text="190/121")],
                )
            )

    response = ClinicalAnalyticsService(OneRecord()).analyze()
    assert len(response.signals) == 2
    assert response.signals[0].citation_id.endswith("#structured")
