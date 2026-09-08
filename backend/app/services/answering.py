from typing import Any

from backend.app.core.config import settings
from backend.app.models.retrieval import SearchResult
from backend.app.models.retrieval import EvidenceMetadata


class GroundedAnswerer:
    """Answer only from retrieved evidence; optionally delegates prose to a LangChain chat model."""

    def __init__(self, model: Any | None = None) -> None:
        self.model = model

    def answer(self, question: str, results: list[SearchResult], history: list[dict] | None = None, source_label: str = "your records", evidence: EvidenceMetadata | None = None, query_intent: str | None = None, query_focus: str | None = None) -> tuple[str, str]:
        if not results:
            return "I could not find relevant information in the uploaded records.", "extractive"
        if self.model is not None:
            context = "\n\n".join(
                f"[{item.citation_id} | page={item.source_page or 'unknown'} | date={item.document_date or 'unknown'} | type={item.document_type or 'unknown'}] {item.content}"
                for item in results
            )
            recent_history = "\n".join(f"{item['role']}: {item['content']}" for item in (history or [])[-6:])
            evidence_json = evidence.model_dump_json() if evidence else '{"complete": true}'
            prompt = (
                "You are a careful health-record assistant. Answer the question using only the evidence below. "
                "If the evidence is insufficient, say so. Do not diagnose, invent facts, or give emergency advice. "
                "For broad, historical, or progression questions, use every relevant dated record in the evidence, "
                "sort events from earliest to latest, and identify the latest documented record before describing current status. "
                "Separate confirmed information from what cannot be determined. Distinguish investigations from procedures, "
                "and prescribed medications from current active medications when the evidence allows. "
                "Do not turn temporal sequence into causation: say that one finding occurred after treatment unless the source explicitly documents causation. "
                "Use complete natural sentences for timeline entries; write 'No medication was started at this visit' instead of a fragment such as 'Medication not started'. "
                "Write concise headings and bullets. Cite each bullet or short paragraph once; do not repeat the same citation after every sentence.\n\n"
                f"Evidence metadata: {evidence_json}\n\n"
                f"Query intent: {query_intent or 'general'}\n{query_focus or ''}\n\n"
                f"Recent conversation:\n{recent_history}\n\nQuestion: {question}\n\nEvidence:\n{context}"
            )
            response = self.model.invoke(prompt)
            return self._content_text(getattr(response, "content", response)), "llm"

        excerpts = "\n".join(f"[{item.citation_id} | page={item.source_page or 'unknown'}] {item.content}" for item in results)
        return f"Relevant excerpts from {source_label}:\n{excerpts}", "extractive"

    @staticmethod
    def _content_text(content: Any) -> str:
        """Flatten Gemini/LangChain content blocks into readable answer text."""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                if text:
                    parts.append(str(text))
            return "\n".join(parts).strip()
        return str(content).strip()


def configured_answerer() -> GroundedAnswerer:
    if settings.llm_provider != "google_genai" or not settings.llm_model or not settings.gemini_api_key:
        return GroundedAnswerer()
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_kwargs = {"model": settings.llm_model, "api_key": settings.gemini_api_key}
        if settings.llm_model.startswith("gemini-3"):
            model_kwargs["thinking_level"] = "low"
        model = ChatGoogleGenerativeAI(**model_kwargs)
    except (ImportError, RuntimeError, ValueError):
        return GroundedAnswerer()
    return GroundedAnswerer(model)
