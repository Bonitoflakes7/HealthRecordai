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


def test_normalizer_extracts_rich_clinical_items_conservatively():
    document = DocumentNormalizer().normalize(
        "record-4",
        "SAMPLE MEDICAL RECORD\nDate: 19 January 2025\n"
        "Assessment\nPersistent hyperlipidemia with elevated cardiovascular risk.\n"
        "Medication Started\nAtorvastatin 10 mg once daily, as prescribed by the physician.\n"
        "Monitoring\nLipid panel and liver function testing recommended after initiation.\n"
        "Procedures\nNo procedures performed.",
    )

    assert document.conditions[0].name.startswith("Persistent hyperlipidemia")
    assert document.conditions[0].status == "active"
    assert document.medications[0].name == "Atorvastatin"
    assert document.medications[0].dose == "10 mg"
    assert document.medications[0].action == "started"
    assert document.medications[0].status == "active"
    assert document.investigations[0].status == "recommended"
    assert document.procedures == []


def test_normalizer_preserves_multiple_dates_and_builds_clinical_events():
    document = DocumentNormalizer().normalize(
        "record-5",
        "CHRONIC CARE NOTE\nDate of Visit: 2024-01-14\n"
        "Assessment\nMechanical lower back pain.\n"
        "Medication\nParacetamol 500 mg twice daily.\n"
        "Follow-up\nReviewed on March 3, 2024; return visit planned for 2024/06/18.",
    )

    assert str(document.document_date) == "2024-01-14"
    assert [str(item.value) for item in document.date_candidates] == ["2024-01-14", "2024-03-03", "2024-06-18"]
    assert any(item.event_type == "condition" and item.event_date.isoformat() == "2024-01-14" for item in document.clinical_events)
    assert any(item.event_type == "medication" and item.event_date.isoformat() == "2024-01-14" for item in document.clinical_events)
