from backend.app.services.retrieval import LocalRecordIndex


def test_local_index_replaces_previous_record_chunks(tmp_path):
    index = LocalRecordIndex(tmp_path / "chunks.json")
    index.index_record("record-1", "notes.txt", "Blood pressure was 120/80.")
    index.index_record("record-1", "notes.txt", "Heart rate was 72 bpm.")

    results = index.search("blood pressure")
    assert results == []
    assert index.search("heart rate")[0].citation_id == "record-1#chunk-0"


def test_search_can_filter_to_one_record(tmp_path):
    index = LocalRecordIndex(tmp_path / "chunks.json")
    index.index_record("record-1", "one.txt", "Glucose was 100 mg/dL.")
    index.index_record("record-2", "two.txt", "Glucose was 140 mg/dL.")

    results = index.search("glucose", record_id="record-2")
    assert len(results) == 1
    assert results[0].record_id == "record-2"


def test_numeric_only_query_does_not_create_false_match(tmp_path):
    index = LocalRecordIndex(tmp_path / "chunks.json")
    index.index_record("record-1", "notes.txt", "The visit lasted 5 minutes.")

    assert index.search("5") == []


def test_longitudinal_search_returns_deterministic_completeness_metadata(tmp_path):
    index = LocalRecordIndex(tmp_path / "chunks.json")
    index.index_record("record-1", "jan.txt", "Back pain visit.", document_date="2024-01-14", document_type="clinical_note")
    index.index_record("record-2", "mar.txt", "Glucose 118.", document_date="2025-03-11", document_type="lab_report")

    results, metadata = index.search_all(limit=60)

    assert [item.record_id for item in results] == ["record-1", "record-2"]
    assert metadata.records_available == 2
    assert metadata.records_retrieved == 2
    assert metadata.complete is True
    assert metadata.earliest_record_date == "2024-01-14"
    assert metadata.latest_record_date == "2025-03-11"
    assert metadata.latest_record_id == "record-2"


def test_index_search_returns_source_page_for_page_aware_records(tmp_path):
    index = LocalRecordIndex(tmp_path / "chunks.json", chunk_size=1000)
    index.index_record("record-1", "multi.pdf", "", page_texts=["Assessment: back pain", "Medication: Ibuprofen 200 mg"])

    result = index.search("Ibuprofen")[0]
    assert result.source_page == 2
