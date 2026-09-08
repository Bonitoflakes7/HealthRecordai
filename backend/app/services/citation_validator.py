import re

from backend.app.models.retrieval import SearchResult
from backend.app.models.validation import CitationValidation


_STOPWORDS = {"about", "after", "also", "based", "been", "from", "have", "that", "their", "there", "these", "they", "this", "what", "when", "which", "with", "your"}


def validate_answer(answer: str, results: list[SearchResult]) -> CitationValidation:
    if not results:
        return CitationValidation()
    known = {item.citation_id: item for item in results}
    found: list[str] = []
    invalid: list[str] = []
    for raw in re.findall(r"\[([^\]\n]+)\]", answer):
        citation_id = raw.split(" |", 1)[0].strip()
        if "#chunk-" not in citation_id:
            continue
        if citation_id in known and citation_id not in found:
            found.append(citation_id)
        elif citation_id not in invalid:
            invalid.append(citation_id)

    claim_lines = []
    for line in re.split(r"\n+", answer):
        clean = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if not clean or clean.startswith("Relevant excerpts") or clean.endswith(":"):
            continue
        if re.search(r"[A-Za-z]{3}", clean):
            claim_lines.append(clean)
    uncited = [line for line in claim_lines if "#chunk-" not in line]
    unsupported: list[str] = []
    evidence_text = " ".join(item.content.casefold() for item in results)
    for line in claim_lines:
        if "#chunk-" not in line:
            continue
        claim_words = {word for word in re.findall(r"[a-z0-9]+", re.sub(r"\[[^\]]+\]", "", line).casefold()) if len(word) > 2 and word not in _STOPWORDS}
        if claim_words and not any(word in evidence_text for word in claim_words):
            unsupported.append(line)
    warnings = []
    if invalid:
        warnings.append("The answer contains citation IDs that were not present in retrieved evidence.")
    if uncited:
        warnings.append("One or more answer statements do not include a citation.")
    if unsupported:
        warnings.append("One or more cited statements have little lexical overlap with the retrieved evidence and need review.")
    if invalid or uncited or unsupported:
        status = "review"
    elif found:
        status = "passed"
    else:
        status = "review"
        warnings.append("No verifiable citation was found in the answer.")
    return CitationValidation(status=status, valid_citations=found, invalid_citations=invalid, uncited_claims=uncited, unsupported_claims=unsupported, warnings=warnings)
