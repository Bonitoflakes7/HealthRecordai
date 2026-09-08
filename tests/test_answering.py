from backend.app.models.retrieval import SearchResult
from backend.app.services.answering import GroundedAnswerer


def test_fallback_answer_is_citation_aware():
    result = SearchResult(
        citation_id="record-1#chunk-0",
        record_id="record-1",
        filename="notes.txt",
        chunk_index=0,
        content="Blood pressure was 120/80.",
        score=1.0,
    )

    answer, mode = GroundedAnswerer().answer("What was the blood pressure?", [result])

    assert mode == "extractive"
    assert "record-1#chunk-0" in answer
    assert "120/80" in answer


def test_empty_evidence_is_explicit():
    answer, mode = GroundedAnswerer().answer("What happened?", [])

    assert mode == "extractive"
    assert "could not find" in answer


def test_answerer_flattens_gemini_content_blocks():
    content = [{"type": "text", "text": "First line."}, {"type": "text", "text": "Second line."}]
    assert GroundedAnswerer._content_text(content) == "First line.\nSecond line."
