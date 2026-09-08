from backend.app.services.conversations import ConversationStore


def test_conversation_store_persists_turns(tmp_path):
    store = ConversationStore(tmp_path)
    conversation = store.create()
    store.append(conversation.id, "user", "What did my report say?")
    store.append(conversation.id, "assistant", "Relevant excerpts.", ["record-1#chunk-0"])

    loaded = store.get(conversation.id)
    assert loaded is not None
    assert [message.role for message in loaded.messages] == ["user", "assistant"]
    assert loaded.messages[-1].citation_ids == ["record-1#chunk-0"]
