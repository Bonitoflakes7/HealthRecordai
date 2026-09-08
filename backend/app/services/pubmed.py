import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from backend.app.models.retrieval import SearchResult


class LiteratureUnavailable(RuntimeError):
    pass


class PubMedClient:
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, cache_dir: Path, email: str | None = None, timeout: int = 15) -> None:
        self.cache_dir = cache_dir.resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.email = email
        self.timeout = timeout

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        cache_path = self._cache_path(query, limit)
        try:
            ids = self._get_json("esearch.fcgi", {"db": "pubmed", "term": query, "retmode": "json", "retmax": limit})["esearchresult"]["idlist"]
            if not ids:
                return []
            results = self._parse_abstracts(self._get_text("efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}))
            cache_path.write_text(json.dumps([item.model_dump() for item in results], indent=2), encoding="utf-8")
            return results
        except (LiteratureUnavailable, urllib.error.URLError, TimeoutError, ValueError, ET.ParseError):
            if cache_path.exists():
                return [SearchResult(**item) for item in json.loads(cache_path.read_text(encoding="utf-8"))]
            raise LiteratureUnavailable("PubMed is unavailable and no cached result exists")

    def _get_json(self, endpoint: str, params: dict) -> dict:
        return json.loads(self._request(endpoint, params))

    def _get_text(self, endpoint: str, params: dict) -> str:
        return self._request(endpoint, params)

    def _request(self, endpoint: str, params: dict) -> str:
        if self.email:
            params["email"] = self.email
        url = f"{self.base_url}/{endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": "HealthRecordAI/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LiteratureUnavailable(str(exc)) from exc

    @staticmethod
    def _parse_abstracts(xml_text: str) -> list[SearchResult]:
        root = ET.fromstring(xml_text)
        results: list[SearchResult] = []
        for article in root.findall(".//PubmedArticle"):
            pmid = (article.findtext(".//PMID") or "").strip()
            title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else "Untitled article"
            abstract = " ".join("".join(node.itertext()).strip() for node in article.findall(".//AbstractText"))
            if not pmid or not abstract:
                continue
            content = f"{title}\n\n{abstract}"
            results.append(
                SearchResult(
                    citation_id=f"pubmed:{pmid}",
                    record_id=f"pubmed:{pmid}",
                    filename=title[:200],
                    chunk_index=0,
                    content=content,
                    score=1.0,
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
            )
        return results

    def _cache_path(self, query: str, limit: int) -> Path:
        key = hashlib.sha256(f"{query.casefold()}:{limit}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.json"
