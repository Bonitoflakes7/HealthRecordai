import re


class SafetyAssessment:
    def __init__(self, level: str = "normal", flags: list[str] | None = None, message: str | None = None) -> None:
        self.level = level
        self.flags = flags or []
        self.message = message


class SafetyChecker:
    _urgent_patterns = {
        "possible_emergency": re.compile(
            r"\b(chest pain|can't breathe|cannot breathe|difficulty breathing|severe bleeding|unconscious|stroke symptoms?)\b",
            re.I,
        ),
        "possible_self_harm": re.compile(
            r"\b(suicid(?:e|al)|kill myself|self[- ]?harm|hurt myself|end my life)\b", re.I
        ),
    }

    def assess(self, text: str) -> SafetyAssessment:
        flags = [name for name, pattern in self._urgent_patterns.items() if pattern.search(text)]
        if not flags:
            return SafetyAssessment()
        return SafetyAssessment(
            level="urgent",
            flags=flags,
            message=(
                "This may describe an urgent safety situation. I cannot assess emergencies. "
                "Please contact your local emergency service or crisis service now, and seek immediate help from a trusted person."
            ),
        )
