from backend.app.services.sqlite_conversations import SqliteConversationStore


def test_sqlite_conversation_store_survives_new_instance(tmp_path):
    database_path = tmp_path / "health.db"
    first = SqliteConversationStore(database_path)
    conversation = first.create()
    first.append(conversation.id, "user", "What did my report say?")
    first.append(conversation.id, "assistant", "Relevant evidence.", ["record-1#chunk-0"])

    second = SqliteConversationStore(database_path)
    loaded = second.get(conversation.id)
    assert loaded is not None
    assert len(loaded.messages) == 2
    assert loaded.messages[-1].citation_ids == ["record-1#chunk-0"]
