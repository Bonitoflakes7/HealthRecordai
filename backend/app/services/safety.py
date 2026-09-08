import re


class SafetyAssessment:
    def __init__(self, level: str = "normal", flags: list[str] | None = None, message: str | None = None) -> None:
        self.level = level
        self.flags = flags or []
        self.message = message


class SafetyChecker:
    """Deterministic first-pass safety intent detection before retrieval or model calls."""

    _urgent_patterns = {
        "possible_emergency": re.compile(
            r"\b(chest\s+(?:pain|pressure|tightness)|can't\s+breathe|cannot\s+breathe|difficulty\s+breathing|severe\s+bleeding|unconscious|fainted|seizure|stroke\s+symptoms?|face\s+(?:is\s+)?drooping|speech\s+(?:is\s+)?slurred|sudden\s+weakness|severe\s+allergic\s+reaction|throat\s+swelling)\b",
            re.I,
        ),
        "possible_self_harm": re.compile(r"\b(suicid(?:e|al)|kill\s+myself|self[- ]?harm|hurt\s+myself|end\s+my\s+life)\b", re.I),
        "possible_overdose": re.compile(r"\b(overdose|overdosed|took\s+too\s+much|poisoned|poisoning|toxic\s+amount)\b", re.I),
    }
    _high_risk_patterns = {
        "medication_change": re.compile(r"\b(stop|stopped|skip|double|increase|decrease|change|replace)\b.{0,35}\b(medication|medicine|drug|dose|tablet|prescription)\b", re.I),
        "drug_interaction": re.compile(r"\b(interact(?:ion|ions)?|safe\s+to\s+take|take\s+with|mix|combine)\b.{0,50}\b(medication|medicine|drug|supplement|alcohol)\b", re.I),
        "pregnancy_risk": re.compile(r"\b(pregnan(?:t|cy)|breastfeeding|nursing)\b", re.I),
        "high_risk_population": re.compile(r"\b(infant|newborn|baby|child|elderly|immunocompromised)\b", re.I),
    }
    _negation = re.compile(r"\b(no|not|without|denies|denied|never)\b", re.I)

    def assess(self, text: str) -> SafetyAssessment:
        urgent_flags = [name for name, pattern in self._urgent_patterns.items() if self._active_match(pattern, text)]
        if urgent_flags:
            return SafetyAssessment(
                level="urgent", flags=urgent_flags,
                message=("This may describe an urgent safety situation. I cannot assess emergencies. "
                          "Please contact your local emergency service or crisis service now, and seek immediate help from a trusted person."),
            )
        high_risk_flags = [name for name, pattern in self._high_risk_patterns.items() if pattern.search(text)]
        if high_risk_flags:
            return SafetyAssessment(
                level="high_risk", flags=high_risk_flags,
                message=("This question may require a clinician or pharmacist who knows your full history. "
                         "Do not start, stop, or change treatment based only on this record assistant."),
            )
        return SafetyAssessment()

    def _active_match(self, pattern: re.Pattern[str], text: str) -> bool:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 28):match.start()]
            if not self._negation.search(prefix):
                return True
        return False
