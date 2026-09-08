from backend.app.models.retrieval import SearchResult
from backend.app.services.answering import GroundedAnswerer
from backend.app.workflows.qa import build_qa_graph


class FakeIndex:
    def search(self, query, record_id=None, limit=5, owner_id=None):
        return [
            SearchResult(
                citation_id="record-1#chunk-0",
                record_id="record-1",
                filename="notes.txt",
                chunk_index=0,
                content="The patient reported fatigue.",
                score=1.0,
            )
        ]


def test_qa_graph_retrieves_before_answering():
    result = build_qa_graph(FakeIndex(), GroundedAnswerer()).invoke(
        {"question": "What did the patient report?", "limit": 5}
    )

    assert result["mode"] == "extractive"
    assert result["results"][0].citation_id == "record-1#chunk-0"


def test_qa_graph_short_circuits_urgent_question():
    result = build_qa_graph(FakeIndex(), GroundedAnswerer()).invoke(
        {"question": "I have chest pain and cannot breathe", "limit": 5}
    )

    assert result["mode"] == "safety"
    assert result["safety_level"] == "urgent"
    assert "results" not in result
