from backend.app.services.query_router import route_question


def test_router_identifies_category_intents():
    assert route_question("What medications were prescribed?").intent == "medications"
    assert route_question("Which lab tests were recommended?").intent == "investigations"
    assert route_question("What procedures were performed?").intent == "procedures"
    assert route_question("What diagnoses are documented?").intent == "conditions"


def test_router_prioritizes_longitudinal_questions():
    route = route_question("Show my complete medication history over time")

    assert route.intent == "longitudinal"
    assert route.longitudinal is True


def test_qa_graph_exposes_query_intent():
    from backend.app.models.retrieval import SearchResult
    from backend.app.services.answering import GroundedAnswerer
    from backend.app.workflows.qa import build_qa_graph

    class FakeIndex:
        def search(self, query, record_id=None, limit=5, owner_id=None):
            return [SearchResult(citation_id="r#chunk-0", record_id="r", filename="note.txt", chunk_index=0, content="Medication started.", score=1)]

    result = build_qa_graph(FakeIndex(), GroundedAnswerer()).invoke({"question": "What medication was started?", "limit": 5})

    assert result["query_intent"] == "medications"
