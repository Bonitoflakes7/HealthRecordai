import json

import pytest

from backend.app.services.pubmed import LiteratureUnavailable, PubMedClient


SEARCH_RESPONSE = json.dumps({"esearchresult": {"idlist": ["12345"]}})
ABSTRACT_RESPONSE = """
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345</PMID>
      <Article>
        <ArticleTitle>Exercise and blood pressure</ArticleTitle>
        <Abstract><AbstractText>Structured exercise may affect blood pressure.</AbstractText></Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_pubmed_search_parses_and_caches_articles(tmp_path, monkeypatch):
    client = PubMedClient(tmp_path)

    def fake_request(endpoint, params):
        return SEARCH_RESPONSE if endpoint.startswith("esearch") else ABSTRACT_RESPONSE

    monkeypatch.setattr(client, "_request", fake_request)
    results = client.search("exercise blood pressure")

    assert results[0].citation_id == "pubmed:12345"
    assert results[0].source_url.endswith("/12345/")
    assert "Structured exercise" in results[0].content
    assert list(tmp_path.glob("*.json"))


def test_pubmed_search_uses_cache_when_network_fails(tmp_path, monkeypatch):
    client = PubMedClient(tmp_path)
    client._cache_path("sleep", 1).write_text(
        json.dumps([{"citation_id": "pubmed:1", "record_id": "pubmed:1", "filename": "Cached", "chunk_index": 0, "content": "Cached abstract", "score": 1.0, "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/"}]),
        encoding="utf-8",
    )

    def fail_request(endpoint, params):
        raise LiteratureUnavailable("offline")

    monkeypatch.setattr(client, "_request", fail_request)
    assert client.search("sleep", 1)[0].citation_id == "pubmed:1"
