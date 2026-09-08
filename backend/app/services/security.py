import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from backend.app.core.config import settings
from backend.app.models.auth import AuditEvent, User


class AuthStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.password_hash = PasswordHash.recommended()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def create_user(self, username: str, password: str) -> User:
        user_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users(id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, username, self.password_hash.hash(password), now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("username already exists") from exc
        return User(id=user_id, username=username)

    def authenticate(self, username: str, password: str) -> User | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or row["disabled"] or not self.password_hash.verify(password, row["password_hash"]):
            return None
        return User(id=row["id"], username=row["username"], disabled=bool(row["disabled"]))

    def get(self, user_id: str) -> User | None:
        with self._connect() as connection:
            row = connection.execute("SELECT id, username, disabled FROM users WHERE id = ?", (user_id,)).fetchone()
        return None if row is None else User(id=row["id"], username=row["username"], disabled=bool(row["disabled"]))


class AuditStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, action TEXT NOT NULL, resource_type TEXT NOT NULL, resource_id TEXT, success INTEGER NOT NULL DEFAULT 1, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def record(self, user_id: str, action: str, resource_type: str, resource_id: str | None = None, success: bool = True, metadata: dict | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(user_id, action, resource_type, resource_id, success, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, action, resource_type, resource_id, int(success), json.dumps(metadata or {}), datetime.now(timezone.utc).isoformat()),
            )

    def list_for_user(self, user_id: str, limit: int = 100) -> list[AuditEvent]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id, user_id, action, resource_type, resource_id, success, created_at FROM audit_events WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, max(1, min(limit, 500)))).fetchall()
        return [AuditEvent(id=row["id"], user_id=row["user_id"], action=row["action"], resource_type=row["resource_type"], resource_id=row["resource_id"], success=bool(row["success"]), created_at=datetime.fromisoformat(row["created_at"])) for row in rows]


def create_access_token(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user.id, "username": user.username, "exp": expires}, settings.auth_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.auth_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
