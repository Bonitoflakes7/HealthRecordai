from backend.app.services.safety import SafetyChecker


def test_safety_checker_flags_urgent_language():
    assessment = SafetyChecker().assess("I have severe bleeding")

    assert assessment.level == "urgent"
    assert assessment.flags == ["possible_emergency"]


def test_safety_checker_leaves_routine_question_normal():
    assert SafetyChecker().assess("What was my glucose result?").level == "normal"


def test_safety_checker_detects_additional_urgent_intents():
    assert "possible_overdose" in SafetyChecker().assess("I took too much of my medication").flags
    assert "possible_emergency" in SafetyChecker().assess("My face is drooping and speech is slurred").flags


def test_safety_checker_detects_high_risk_without_blocking_retrieval():
    assessment = SafetyChecker().assess("Can I stop my medication?")

    assert assessment.level == "high_risk"
    assert "medication_change" in assessment.flags


def test_safety_checker_respects_explicit_negation():
    assert SafetyChecker().assess("I have no chest pain and want to review my record").level == "normal"
