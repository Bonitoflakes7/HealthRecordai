from pydantic import BaseModel, Field

from backend.app.models.retrieval import SearchResult


class LiteratureSearchResponse(BaseModel):
    query: str
    source: str = "pubmed"
    results: list[SearchResult] = Field(default_factory=list)


class LiteratureAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class LiteratureAskResponse(BaseModel):
    question: str
    answer: str
    citations: list[SearchResult] = Field(default_factory=list)
    mode: str
    source: str = "pubmed"
