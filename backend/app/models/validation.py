from pydantic import BaseModel, Field


class CitationValidation(BaseModel):
    status: str = "not_applicable"
    valid_citations: list[str] = Field(default_factory=list)
    invalid_citations: list[str] = Field(default_factory=list)
    uncited_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
