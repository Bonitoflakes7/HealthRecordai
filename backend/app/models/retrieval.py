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


class EvidenceMetadata(BaseModel):
    records_available: int = 0
    records_retrieved: int = 0
    complete: bool = True
    earliest_record_date: str | None = None
    latest_record_date: str | None = None
    latest_record_id: str | None = None
