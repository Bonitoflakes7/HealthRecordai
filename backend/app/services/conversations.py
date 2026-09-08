import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.models.conversation import Conversation, ConversationMessage


class ConversationStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, conversation_id: str) -> Conversation | None:
        path = self._path(conversation_id)
        if not path.exists():
            return None
        return Conversation(**json.loads(path.read_text(encoding="utf-8")))

    def create(self) -> Conversation:
        conversation = Conversation(id=uuid4().hex)
        self._write(conversation)
        return conversation

    def append(self, conversation_id: str, role: str, content: str, citation_ids: list[str] | None = None) -> Conversation:
        conversation = self.get(conversation_id)
        if conversation is None:
            raise ValueError("conversation not found")
        conversation.messages.append(
            ConversationMessage(
                role=role,
                content=content,
                created_at=datetime.now(timezone.utc),
                citation_ids=citation_ids or [],
            )
        )
        self._write(conversation)
        return conversation

    def _path(self, conversation_id: str) -> Path:
        if not conversation_id or "/" in conversation_id or "\\" in conversation_id:
            raise ValueError("invalid conversation id")
        return self.root / f"{conversation_id}.json"

    def _write(self, conversation: Conversation) -> None:
        self._path(conversation.id).write_text(conversation.model_dump_json(indent=2), encoding="utf-8")
