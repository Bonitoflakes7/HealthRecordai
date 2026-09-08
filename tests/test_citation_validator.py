from backend.app.models.retrieval import SearchResult
from backend.app.services.citation_validator import validate_answer


def evidence():
    return [SearchResult(citation_id="record-1#chunk-0", record_id="record-1", filename="note.txt", chunk_index=0, content="Blood pressure was 120/80 mmHg.", score=1)]


def test_validator_passes_known_supported_citation():
    result = validate_answer("Blood pressure was 120/80 mmHg. [record-1#chunk-0]", evidence())

    assert result.status == "passed"
    assert result.valid_citations == ["record-1#chunk-0"]
    assert result.warnings == []


def test_validator_flags_unknown_and_uncited_claims():
    result = validate_answer("Blood pressure was normal. [missing#chunk-4]\nThe patient improved.", evidence())

    assert result.status == "review"
    assert "missing#chunk-4" in result.invalid_citations
    assert result.uncited_claims == ["The patient improved."]


def test_validator_is_not_applicable_without_evidence():
    assert validate_answer("No records found.", []).status == "not_applicable"
