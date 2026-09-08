from pydantic import BaseModel, Field

from backend.app.models.retrieval import EvidenceMetadata, SearchResult
from backend.app.models.validation import CitationValidation


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    record_id: str | None = None
    limit: int = Field(default=5, ge=1, le=10)
    conversation_id: str | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[SearchResult] = Field(default_factory=list)
    mode: str
    conversation_id: str
    safety_level: str = "normal"
    safety_flags: list[str] = Field(default_factory=list)
    evidence: EvidenceMetadata = Field(default_factory=EvidenceMetadata)
    query_intent: str = "general"
    citation_validation: CitationValidation = Field(default_factory=CitationValidation)
    retrieval_mode: str = "lexical"
