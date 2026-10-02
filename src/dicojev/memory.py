"""Private local profiles, chats, and bounded decision history."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def default_data_dir() -> Path:
    configured = os.getenv("DICOJEV_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    if sys.platform == "win32" and os.getenv("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "DiCoJev"
    return Path.home() / ".local" / "share" / "dicojev"


@dataclass(frozen=True)
class ChatSummary:
    id: str
    title: str
    updated_at: str


class LocalMemoryStore:
    """SQLite persistence. It is local-only and intentionally has no authentication."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve() if data_dir else default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "memory.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    chat_id TEXT REFERENCES chats(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    salience REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chats_account_updated
                    ON chats(account_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_turns_chat ON turns(chat_id, id);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def ensure_account(self, account_id: str, display_name: str | None = None) -> None:
        value = account_id.strip() or "default"
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO accounts(id, display_name, created_at) VALUES (?, ?, ?)",
                (value, display_name or value, self._now()),
            )

    def create_chat(self, account_id: str, title: str = "New decision") -> str:
        self.ensure_account(account_id)
        chat_id = uuid.uuid4().hex
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chats(id, account_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, account_id, title.strip()[:80] or "New decision", now, now),
            )
        return chat_id

    def list_chats(self, account_id: str) -> tuple[ChatSummary, ...]:
        self.ensure_account(account_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, updated_at FROM chats WHERE account_id = ? "
                "ORDER BY updated_at DESC",
                (account_id,),
            ).fetchall()
        return tuple(ChatSummary(**dict(row)) for row in rows)

    def append_turn(self, chat_id: str, role: str, content: dict[str, Any]) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO turns(chat_id, role, content_json, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, role, json.dumps(content, ensure_ascii=False), now),
            )
            connection.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))

    def rename_chat(self, chat_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip()[:80] or "New decision", self._now(), chat_id),
            )

    def latest_turn(self, chat_id: str, role: str | None = None) -> dict[str, Any] | None:
        query = "SELECT content_json FROM turns WHERE chat_id = ?"
        parameters: list[Any] = [chat_id]
        if role:
            query += " AND role = ?"
            parameters.append(role)
        query += " ORDER BY id DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return json.loads(row["content_json"]) if row else None

    def decision_history(self, chat_id: str, limit: int = 8) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content_json FROM turns WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, max(0, limit)),
            ).fetchall()
        history = []
        for row in reversed(rows):
            payload = json.loads(row["content_json"])
            summary = payload.get("summary") or payload.get("goal") or payload.get("context")
            if summary:
                history.append(f"{row['role']}: {str(summary)[:1000]}")
        return tuple(history)

    def remember(
        self,
        account_id: str,
        content: str,
        *,
        chat_id: str | None = None,
        kind: str = "note",
        salience: float = 0.5,
    ) -> None:
        self.ensure_account(account_id)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memories(account_id, chat_id, kind, content, salience, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (account_id, chat_id, kind, content, min(1.0, max(0.0, salience)), self._now()),
            )
