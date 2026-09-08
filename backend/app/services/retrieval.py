import json
import os
import re
import tempfile
import time
from pathlib import Path

from langchain_core.documents import Document

from backend.app.core.config import settings
from backend.app.models.retrieval import EvidenceMetadata, SearchResult


class LocalRecordIndex:
    """Small persistent lexical index with LangChain-compatible Documents and citations."""

    def __init__(self, root: Path | None = None, chunk_size: int = 900, semantic_model=None) -> None:
        self.index_path = (root or settings.data_dir / "rag" / "chunks.json").resolve()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self.semantic_model = semantic_model if semantic_model is not None else self._load_semantic_model()
        self._semantic_cache: dict[str, list[float]] = {}

    @property
    def retrieval_mode(self) -> str:
        return "hybrid" if self.semantic_model is not None else "lexical"

    @staticmethod
    def _load_semantic_model():
        if not settings.semantic_retrieval_enabled:
            return None
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(settings.semantic_model_name)
        except (ImportError, OSError, RuntimeError, ValueError):
            return None

    def index_record(self, record_id: str, filename: str, text: str, owner_id: str = "dev-user", document_date: str | None = None, document_type: str | None = None, page_texts: list[str] | None = None) -> int:
        documents = self._chunk(record_id, filename, text, owner_id, document_date, document_type, page_texts)
        existing = [item for item in self._read() if item["metadata"].get("record_id") != record_id]
        existing.extend(self._serialize(document) for document in documents)
        self._write_index(existing)
        return len(documents)

    def _write_index(self, items: list[dict]) -> None:
        """Replace the index atomically so reloads never write directly to the live file."""
        payload = json.dumps(items, indent=2)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.index_path.parent, prefix="chunks-", suffix=".tmp", delete=False) as temporary:
                temporary.write(payload)
                temporary_path = temporary.name
            last_error: PermissionError | None = None
            for attempt in range(5):
                try:
                    os.replace(temporary_path, self.index_path)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.1 * (attempt + 1))
            if last_error is not None:
                raise last_error
            temporary_path = None
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

    def search(self, query: str, record_id: str | None = None, limit: int = 5, owner_id: str | None = None) -> list[SearchResult]:
        terms = self._tokens(query)
        if not terms and self.semantic_model is None:
            return []
        phrase = query.casefold().strip()
        query_vector = self._encode(query) if self.semantic_model is not None else None
        ranked: list[tuple[float, dict]] = []
        for item in self._read():
            metadata = item["metadata"]
            if record_id and metadata.get("record_id") != record_id:
                continue
            if owner_id is not None and metadata.get("owner_id") != owner_id:
                continue
            content = item["page_content"]
            content_terms = self._tokens(content)
            matched = sum(term in content_terms for term in terms)
            lexical_score = matched / len(terms) if terms else 0.0
            semantic_score = self._cosine(query_vector, self._document_vector(item)) if query_vector is not None else 0.0
            if not matched and semantic_score < 0.15:
                continue
            score = lexical_score
            if phrase and phrase in content.casefold():
                score += 0.5
            if self.semantic_model is not None:
                weight = min(1.0, max(0.0, settings.semantic_retrieval_weight))
                score = ((1 - weight) * min(score, 1.0)) + (weight * semantic_score)
            ranked.append((score, item))

        ranked.sort(key=lambda value: value[0], reverse=True)
        results: list[SearchResult] = []
        for score, item in ranked[: max(1, min(limit, 20))]:
            metadata = item["metadata"]
            chunk_index = int(metadata["chunk_index"])
            results.append(
                SearchResult(
                    citation_id=f"{metadata['record_id']}#chunk-{chunk_index}",
                    record_id=metadata["record_id"],
                    filename=metadata["filename"],
                    chunk_index=chunk_index,
                    content=item["page_content"],
                    score=round(score, 4),
                    document_date=metadata.get("document_date"),
                    document_type=metadata.get("document_type"),
                    source_page=metadata.get("source_page"),
                )
            )
        return results

    def _encode(self, text: str) -> list[float]:
        encoded = self.semantic_model.encode([text], normalize_embeddings=True)[0]
        return [float(value) for value in (encoded.tolist() if hasattr(encoded, "tolist") else encoded)]

    def _document_vector(self, item: dict) -> list[float]:
        key = f"{item['metadata'].get('record_id')}#{item['metadata'].get('chunk_index')}"
        if key not in self._semantic_cache:
            self._semantic_cache[key] = self._encode(item["page_content"])
        return self._semantic_cache[key]

    @staticmethod
    def _cosine(left: list[float] | None, right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))

    def search_all(self, owner_id: str | None = None, limit: int = 60) -> tuple[list[SearchResult], EvidenceMetadata]:
        """Return a date-ordered evidence set for longitudinal questions."""
        items = [item for item in self._read() if owner_id is None or item["metadata"].get("owner_id") == owner_id]
        record_ids = {item["metadata"].get("record_id") for item in items}
        dates = sorted({item["metadata"].get("document_date") for item in items if item["metadata"].get("document_date")})
        items.sort(key=lambda item: (item["metadata"].get("document_date") or "9999-12-31", item["metadata"].get("record_id", "")))
        results: list[SearchResult] = []
        for item in items[: max(1, min(limit, 100))]:
            metadata = item["metadata"]
            results.append(SearchResult(citation_id=f"{metadata['record_id']}#chunk-{int(metadata['chunk_index'])}", record_id=metadata["record_id"], filename=metadata["filename"], chunk_index=int(metadata["chunk_index"]), content=item["page_content"], score=1.0, document_date=metadata.get("document_date"), document_type=metadata.get("document_type"), source_page=metadata.get("source_page")))
        latest = next((item for item in reversed(items) if item["metadata"].get("document_date")), None)
        metadata = EvidenceMetadata(
            records_available=len(record_ids),
            records_retrieved=len({item.record_id for item in results}),
            complete=len(record_ids) <= max(1, limit),
            earliest_record_date=dates[0] if dates else None,
            latest_record_date=latest["metadata"].get("document_date") if latest else None,
            latest_record_id=latest["metadata"].get("record_id") if latest else None,
        )
        return results, metadata

    def _chunk(self, record_id: str, filename: str, text: str, owner_id: str, document_date: str | None, document_type: str | None, page_texts: list[str] | None = None) -> list[Document]:
        sources = [(page, content) for page, content in enumerate(page_texts or [text], start=1) if content.strip()]
        chunks: list[str] = []
        page_numbers: list[int] = []
        for page, content in sources:
            words = re.sub(r"\s+", " ", content).strip().split(" ")
            current: list[str] = []
            current_length = 0
            for word in words:
                proposed_length = current_length + len(word) + (1 if current else 0)
                if current and proposed_length > self.chunk_size:
                    chunks.append(" ".join(current)); page_numbers.append(page); current = []; current_length = 0
                current.append(word); current_length += len(word) + (1 if current_length else 0)
            if current:
                chunks.append(" ".join(current)); page_numbers.append(page)
        return [Document(id=f"{record_id}#chunk-{index}", page_content=chunk, metadata={"record_id": record_id, "filename": filename, "chunk_index": index, "owner_id": owner_id, "document_date": document_date, "document_type": document_type, "source_page": page_numbers[index]}) for index, chunk in enumerate(chunks)]

    @staticmethod
    def _tokens(value: str) -> set[str]:
        stopwords = {"what", "did", "the", "are", "is", "was", "my", "in", "on", "of", "and", "a", "an", "to", "from", "your", "records", "mentioned"}
        return {token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) > 1 and not token.isdigit() and token not in stopwords}

    @staticmethod
    def _serialize(document: Document) -> dict:
        return {"page_content": document.page_content, "metadata": document.metadata}

    def _read(self) -> list[dict]:
        if not self.index_path.exists():
            return []
        return json.loads(self.index_path.read_text(encoding="utf-8"))
