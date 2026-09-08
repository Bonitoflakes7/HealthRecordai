from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.models.retrieval import EvidenceMetadata, SearchResult
from backend.app.services.answering import GroundedAnswerer
from backend.app.services.retrieval import LocalRecordIndex
from backend.app.services.safety import SafetyChecker


LONGITUDINAL_TERMS = {
    "complete history", "medical history", "chronological", "timeline", "over time", "progression",
    "latest", "current status", "all medications", "every medication", "all conditions", "what improved",
    "what has improved", "from the first", "from beginning", "entire history", "complete summary",
}


def is_longitudinal_question(question: str) -> bool:
    lowered = question.casefold()
    return any(term in lowered for term in LONGITUDINAL_TERMS)


class QAState(TypedDict, total=False):
    question: str
    record_id: str | None
    limit: int
    results: list[SearchResult]
    answer: str
    mode: str
    history: list[dict]
    safety_level: str
    safety_flags: list[str]
    safety_message: str | None
    owner_id: str | None
    evidence: EvidenceMetadata


def build_qa_graph(index: LocalRecordIndex, answerer: GroundedAnswerer, safety_checker: SafetyChecker | None = None):
    checker = safety_checker or SafetyChecker()

    def safety(state: QAState) -> QAState:
        assessment = checker.assess(state["question"])
        return {
            "safety_level": assessment.level,
            "safety_flags": assessment.flags,
            "safety_message": assessment.message,
        }

    def after_safety(state: QAState):
        return "stop" if state.get("safety_level") == "urgent" else "retrieve"

    def retrieve(state: QAState) -> QAState:
        owner_id = state.get("owner_id")
        if state.get("record_id") is None and is_longitudinal_question(state["question"]):
            results, evidence = index.search_all(owner_id=owner_id, limit=60)
            return {"results": results, "evidence": evidence}
        results = index.search(state["question"], record_id=state.get("record_id"), limit=state.get("limit", 5), owner_id=owner_id)
        return {"results": results, "evidence": EvidenceMetadata(records_available=len({item.record_id for item in results}), records_retrieved=len({item.record_id for item in results}), complete=True)}

    def answer(state: QAState) -> QAState:
        text, mode = answerer.answer(state["question"], state.get("results", []), state.get("history", []), evidence=state.get("evidence"))
        return {"answer": text, "mode": mode}

    builder = StateGraph(QAState)
    builder.add_node("safety", safety)
    builder.add_node("retrieve", retrieve)
    builder.add_node("answer", answer)
    builder.add_node("stop", lambda state: {"answer": state.get("safety_message", "Please seek immediate help."), "mode": "safety"})
    builder.add_edge(START, "safety")
    builder.add_conditional_edges("safety", after_safety, {"retrieve": "retrieve", "stop": "stop"})
    builder.add_edge("retrieve", "answer")
    builder.add_edge("stop", END)
    builder.add_edge("answer", END)
    return builder.compile()
