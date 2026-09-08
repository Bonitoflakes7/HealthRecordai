import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.models.conversation import Conversation, ConversationMessage


class SqliteConversationStore:
    """Durable conversation store for the local single-user development deployment."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, owner_id TEXT NOT NULL DEFAULT 'dev-user')")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()}
            if "owner_id" not in columns:
                connection.execute("ALTER TABLE conversations ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'dev-user'")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conversation_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id), role TEXT NOT NULL CHECK(role IN ('user', 'assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL, citation_ids TEXT NOT NULL DEFAULT '[]')"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(conversation_id, id)")

    def create(self, owner_id: str = "dev-user") -> Conversation:
        conversation_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("INSERT INTO conversations(id, created_at, updated_at, owner_id) VALUES (?, ?, ?, ?)", (conversation_id, now, now, owner_id))
        return Conversation(id=conversation_id, owner_id=owner_id)

    def get(self, conversation_id: str, owner_id: str | None = None) -> Conversation | None:
        with self._connect() as connection:
            query = "SELECT id, owner_id FROM conversations WHERE id = ?"
            parameters: tuple = (conversation_id,)
            if owner_id is not None:
                query += " AND owner_id = ?"
                parameters += (owner_id,)
            conversation = connection.execute(query, parameters).fetchone()
            if conversation is None:
                return None
            rows = connection.execute("SELECT role, content, created_at, citation_ids FROM conversation_messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)).fetchall()
        return Conversation(
            id=conversation_id,
            owner_id=conversation["owner_id"],
            messages=[ConversationMessage(role=row["role"], content=row["content"], created_at=datetime.fromisoformat(row["created_at"]), citation_ids=json.loads(row["citation_ids"])) for row in rows],
        )

    def append(self, conversation_id: str, role: str, content: str, citation_ids: list[str] | None = None, owner_id: str | None = None) -> Conversation:
        if self.get(conversation_id, owner_id) is None:
            raise ValueError("conversation not found")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("INSERT INTO conversation_messages(conversation_id, role, content, created_at, citation_ids) VALUES (?, ?, ?, ?, ?)", (conversation_id, role, content, now, json.dumps(citation_ids or [])))
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return self.get(conversation_id, owner_id)  # type: ignore[return-value]
