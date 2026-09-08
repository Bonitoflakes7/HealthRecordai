from pathlib import Path

from backend.app.models.clinical import NormalizedDocument
from backend.app.workflows.ingestion import build_ingestion_graph


class FakeExtractor:
    def extract(self, path: Path, source_type: str) -> str:
        return "LABORATORY REPORT\nBlood pressure: 120/80 mmHg"


class FailingExtractor:
    def extract(self, path: Path, source_type: str) -> str:
        from backend.app.services.extraction import ExtractionError

        raise ExtractionError("test extraction failure")


def test_ingestion_graph_extracts_then_normalizes():
    result = build_ingestion_graph(FakeExtractor()).invoke(
        {"record_id": "record-1", "source_path": "unused.txt", "source_type": "text"}
    )

    assert result["text"].startswith("LABORATORY")
    assert NormalizedDocument.model_validate(result["structured"]).document_type == "lab_report"


def test_ingestion_graph_stops_on_extraction_failure():
    result = build_ingestion_graph(FailingExtractor()).invoke(
        {"record_id": "record-2", "source_path": "unused.txt", "source_type": "text"}
    )

    assert result["error"] == "test extraction failure"
    assert "structured" not in result
