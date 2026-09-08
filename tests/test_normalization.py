from backend.app.services.normalization import DocumentNormalizer


def test_normalizer_classifies_and_extracts_conservative_observations():
    document = DocumentNormalizer().normalize(
        "record-1",
        "LABORATORY REPORT\nDate: 2026-01-14\nBlood pressure: 120/80 mmHg\nHeart rate: 72 bpm\n",
    )

    assert document.document_type == "lab_report"
    assert str(document.document_date) == "2026-01-14"
    assert {item.name for item in document.observations} == {"blood_pressure", "heart_rate"}
    assert document.observations[0].source_text


def test_normalizer_does_not_invent_empty_structure():
    document = DocumentNormalizer().normalize("record-2", "A short note with no known fields.")

    assert document.document_type == "unknown"
    assert document.document_date is None
    assert document.observations == []


def test_normalizer_handles_markdown_consultation_report():
    document = DocumentNormalizer().normalize(
        "record-3",
        "**SAMPLE MEDICAL CONSULTATION REPORT**\nDate of Visit: 07 September 2026\n**Vital Signs**\nPulse Rate: 76 bpm\n**DISCLAIMER:** This is not a prescription.",
    )

    assert document.document_type == "clinical_note"
    assert str(document.document_date) == "2026-09-07"
    assert document.observations[0].name == "heart_rate"
    assert document.sections[0].heading == "SAMPLE MEDICAL CONSULTATION REPORT"
