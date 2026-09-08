from dataclasses import dataclass


@dataclass(frozen=True)
class QueryRoute:
    intent: str
    longitudinal: bool
    focus: str


_LONGITUDINAL = (
    "complete history", "medical history", "chronological", "timeline", "over time", "progression",
    "latest", "current status", "all medications", "every medication", "all conditions", "what improved",
    "from the first", "from beginning", "entire history", "complete summary",
)


def route_question(question: str) -> QueryRoute:
    lowered = question.casefold()
    longitudinal = any(term in lowered for term in _LONGITUDINAL)
    if longitudinal:
        return QueryRoute("longitudinal", True, "Use every relevant dated record, earliest to latest, and identify the latest documented state.")
    categories = (
        ("medications", ("medication", "medicine", "drug", "prescription", "dose", "dosage", "tablet"), "Distinguish prescribed, started, continued, and current medication status."),
        ("investigations", ("test", "lab", "laboratory", "blood work", "imaging", "scan", "result"), "Distinguish recommended, ordered, and completed investigations and include results only when documented."),
        ("procedures", ("procedure", "surgery", "operation", "intervention"), "Distinguish planned, performed, and documented procedures."),
        ("conditions", ("condition", "diagnosis", "diagnoses", "diagnosed", "problem", "symptom", "disease"), "Report documented conditions and their status without inferring a diagnosis."),
    )
    for intent, terms, focus in categories:
        if any(term in lowered for term in terms):
            return QueryRoute(intent, False, focus)
    return QueryRoute("general", False, "Answer from the retrieved record evidence and distinguish documented facts from uncertainty.")
