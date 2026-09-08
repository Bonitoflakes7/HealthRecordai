from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    citation_id: str
    record_id: str
    filename: str
    chunk_index: int
    content: str
    score: float
    source_url: str | None = None
    document_date: str | None = None
    document_type: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult] = Field(default_factory=list)
