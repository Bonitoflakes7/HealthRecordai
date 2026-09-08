from backend.app.services.safety import SafetyChecker


def test_safety_checker_flags_urgent_language():
    assessment = SafetyChecker().assess("I have severe bleeding")

    assert assessment.level == "urgent"
    assert assessment.flags == ["possible_emergency"]


def test_safety_checker_leaves_routine_question_normal():
    assert SafetyChecker().assess("What was my glucose result?").level == "normal"
