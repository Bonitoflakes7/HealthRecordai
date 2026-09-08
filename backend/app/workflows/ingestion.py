from pathlib import Path
from typing import Any, Literal
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.app.models.clinical import NormalizedDocument
from backend.app.models.schemas import SourceType
from backend.app.services.extraction import DocumentExtractor, ExtractionError
from backend.app.services.normalization import DocumentNormalizer


class IngestionState(TypedDict, total=False):
    record_id: str
    source_path: str
    source_type: SourceType
    text: str
    structured: dict[str, Any]
    error: str


def build_ingestion_graph(
    extractor: DocumentExtractor | None = None,
    normalizer: DocumentNormalizer | None = None,
):
    document_extractor = extractor or DocumentExtractor()
    document_normalizer = normalizer or DocumentNormalizer()

    def extract(state: IngestionState) -> IngestionState:
        try:
            text = document_extractor.extract(
                path=Path(state["source_path"]),
                source_type=state["source_type"],
            )
            return {"text": text}
        except (ExtractionError, UnicodeDecodeError) as exc:
            return {"error": str(exc)}

    def normalize(state: IngestionState) -> IngestionState:
        structured = document_normalizer.normalize(state["record_id"], state["text"])
        return {"structured": structured.model_dump(mode="json")}

    def after_extract(state: IngestionState) -> Literal["normalize", END]:
        return "normalize" if state.get("text") and not state.get("error") else END

    builder = StateGraph(IngestionState)
    builder.add_node("extract", extract)
    builder.add_node("normalize", normalize)
    builder.add_edge(START, "extract")
    builder.add_conditional_edges("extract", after_extract)
    builder.add_edge("normalize", END)
    return builder.compile()
