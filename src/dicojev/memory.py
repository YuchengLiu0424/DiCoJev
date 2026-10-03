"""Private local profiles, chats, and bounded decision history."""

from __future__ import annotations

import json
import os
import re
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


@dataclass(frozen=True)
class StoredTurn:
    id: int
    role: str
    content: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class UsageSummary:
    model: str
    chat_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    calls: int


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str
    root_path: str


@dataclass(frozen=True)
class ModelDefinition:
    id: str
    name: str
    role: str
    deployment: str
    adapter: str
    location: str
    model_identifier: str = ""


@dataclass(frozen=True)
class ChatModelSelection:
    language_model_id: str | None
    decision_model_id: str | None


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
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    chat_id TEXT REFERENCES chats(id) ON DELETE SET NULL,
                    model TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_projects (
                    chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS model_registry (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('language', 'decision')),
                    deployment TEXT NOT NULL CHECK(deployment IN ('local', 'online')),
                    adapter TEXT NOT NULL,
                    location TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(account_id, name, role)
                );
                CREATE TABLE IF NOT EXISTS chat_models (
                    chat_id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
                    language_model_id TEXT REFERENCES model_registry(id) ON DELETE SET NULL,
                    decision_model_id TEXT REFERENCES model_registry(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chats_account_updated
                    ON chats(account_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_turns_chat ON turns(chat_id, id);
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(model_registry)")
            }
            if "model_identifier" not in columns:
                connection.execute(
                    "ALTER TABLE model_registry ADD COLUMN model_identifier TEXT NOT NULL DEFAULT ''"
                )
            unnamed = connection.execute(
                "SELECT id FROM chats WHERE title = 'New decision' ORDER BY created_at"
            ).fetchall()
            for index, row in enumerate(unnamed, start=1):
                connection.execute(
                    "UPDATE chats SET title = ? WHERE id = ?", (f"Chat {index}", row["id"])
                )
            account_rows = connection.execute("SELECT id FROM accounts").fetchall()
            for account_row in account_rows:
                self._seed_defaults(connection, account_row["id"])

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
            self._seed_defaults(connection, value)

    def _seed_defaults(self, connection: sqlite3.Connection, account_id: str) -> None:
        now = self._now()
        defaults = (
            (
                f"{account_id}:diffusiongemma-local",
                "DiffusionGemma Local",
                "language",
                "local",
                "diffusiongemma",
                "http://127.0.0.1:11434",
            ),
            (
                f"{account_id}:laya-local",
                "Laya Local",
                "decision",
                "local",
                "laya_local",
                "http://127.0.0.1:8000",
            ),
        )
        for model_id, name, role, deployment, adapter, location in defaults:
            connection.execute(
                "INSERT OR IGNORE INTO model_registry(id, account_id, name, role, deployment, "
                "adapter, location, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (model_id, account_id, name, role, deployment, adapter, location, now),
            )

    def create_chat(
        self, account_id: str, title: str | None = None, project_id: str | None = None
    ) -> str:
        self.ensure_account(account_id)
        if title is None:
            numbered = [
                int(match.group(1))
                for chat in self.list_chats(account_id, project_id)
                if (match := re.fullmatch(r"Chat (\d+)", chat.title))
            ]
            title = f"Chat {max(numbered, default=0) + 1}"
        chat_id = uuid.uuid4().hex
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO chats(id, account_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (chat_id, account_id, title.strip()[:80] or "Untitled chat", now, now),
            )
            if project_id:
                connection.execute(
                    "INSERT INTO chat_projects(chat_id, project_id) VALUES (?, ?)",
                    (chat_id, project_id),
                )
            defaults = connection.execute(
                "SELECT id, role FROM model_registry WHERE account_id = ? AND name IN "
                "('DiffusionGemma Local', 'Laya Local')",
                (account_id,),
            ).fetchall()
            by_role = {row["role"]: row["id"] for row in defaults}
            connection.execute(
                "INSERT INTO chat_models(chat_id, language_model_id, decision_model_id) "
                "VALUES (?, ?, ?)",
                (chat_id, by_role.get("language"), by_role.get("decision")),
            )
        return chat_id

    def list_chats(self, account_id: str, project_id: str | None = None) -> tuple[ChatSummary, ...]:
        self.ensure_account(account_id)
        with self._connect() as connection:
            if project_id:
                rows = connection.execute(
                    "SELECT c.id, c.title, c.updated_at FROM chats c JOIN chat_projects cp "
                    "ON cp.chat_id = c.id WHERE c.account_id = ? AND cp.project_id = ? "
                    "ORDER BY c.updated_at DESC",
                    (account_id, project_id),
                ).fetchall()
            else:
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
                (title.strip()[:80] or "Untitled chat", self._now(), chat_id),
            )

    def delete_chat(self, chat_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    def list_turns(self, chat_id: str, limit: int = 100) -> tuple[StoredTurn, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, role, content_json, created_at FROM turns WHERE chat_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (chat_id, max(0, limit)),
            ).fetchall()
        return tuple(
            StoredTurn(
                id=row["id"],
                role=row["role"],
                content=json.loads(row["content_json"]),
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        )

    def record_usage(
        self,
        account_id: str,
        chat_id: str | None,
        model: str,
        operation: str,
        usage: dict[str, Any],
    ) -> None:
        prompt = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        completion = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        total = int(usage.get("total_tokens", prompt + completion) or prompt + completion)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO usage_events(account_id, chat_id, model, operation, input_tokens, "
                "output_tokens, total_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, chat_id, model, operation, prompt, completion, total, self._now()),
            )

    def usage_summary(self, account_id: str) -> tuple[UsageSummary, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT model, chat_id, SUM(input_tokens) input_tokens, "
                "SUM(output_tokens) output_tokens, SUM(total_tokens) total_tokens, COUNT(*) calls "
                "FROM usage_events WHERE account_id = ? GROUP BY model, chat_id "
                "ORDER BY total_tokens DESC",
                (account_id,),
            ).fetchall()
        return tuple(UsageSummary(**dict(row)) for row in rows)

    def create_project(self, account_id: str, name: str | None = None, root_path: str = "") -> str:
        self.ensure_account(account_id)
        if name is None:
            name = f"Project {len(self.list_projects(account_id)) + 1}"
        project_id = uuid.uuid4().hex
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects(id, account_id, name, root_path, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, account_id, name.strip()[:80], root_path, now, now),
            )
        return project_id

    def list_projects(self, account_id: str) -> tuple[ProjectSummary, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, root_path FROM projects WHERE account_id = ? ORDER BY name",
                (account_id,),
            ).fetchall()
        return tuple(ProjectSummary(**dict(row)) for row in rows)

    def rename_project(self, project_id: str, name: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (name.strip()[:80] or "Untitled project", self._now(), project_id),
            )

    def set_project_folder(self, project_id: str, root_path: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE projects SET root_path=?, updated_at=? WHERE id=?",
                (root_path, self._now(), project_id),
            )

    def delete_project(self, project_id: str) -> None:
        with self._connect() as connection:
            chat_rows = connection.execute(
                "SELECT chat_id FROM chat_projects WHERE project_id = ?", (project_id,)
            ).fetchall()
            for row in chat_rows:
                connection.execute("DELETE FROM chats WHERE id = ?", (row["chat_id"],))
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def set_chat_project(self, chat_id: str, project_id: str | None) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chat_projects WHERE chat_id = ?", (chat_id,))
            if project_id:
                connection.execute(
                    "INSERT INTO chat_projects(chat_id, project_id) VALUES (?, ?)",
                    (chat_id, project_id),
                )

    def get_chat_project(self, chat_id: str) -> ProjectSummary | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT p.id, p.name, p.root_path FROM projects p "
                "JOIN chat_projects cp ON cp.project_id = p.id WHERE cp.chat_id = ?",
                (chat_id,),
            ).fetchone()
        return ProjectSummary(**dict(row)) if row else None

    def add_model(
        self,
        account_id: str,
        *,
        name: str,
        role: str,
        deployment: str,
        adapter: str,
        location: str,
        model_identifier: str = "",
    ) -> str:
        if role not in {"language", "decision"}:
            raise ValueError("model role must be language or decision")
        if deployment not in {"local", "online"}:
            raise ValueError("deployment must be local or online")
        model_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO model_registry(id, account_id, name, role, deployment, adapter, "
                "location, created_at, model_identifier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    model_id,
                    account_id,
                    name.strip()[:80],
                    role,
                    deployment,
                    adapter,
                    location.strip(),
                    self._now(),
                    model_identifier.strip(),
                ),
            )
        return model_id

    def list_models(self, account_id: str, role: str | None = None) -> tuple[ModelDefinition, ...]:
        query = (
            "SELECT id, name, role, deployment, adapter, location, model_identifier FROM model_registry "
            "WHERE account_id = ?"
        )
        parameters: list[Any] = [account_id]
        if role:
            query += " AND role = ?"
            parameters.append(role)
        query += " ORDER BY name"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(ModelDefinition(**dict(row)) for row in rows)

    def delete_model(self, model_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM model_registry WHERE id = ?", (model_id,))

    def update_model(
        self,
        model_id: str,
        *,
        name: str,
        role: str,
        deployment: str,
        adapter: str,
        location: str,
        model_identifier: str = "",
    ) -> None:
        if role not in {"language", "decision"} or deployment not in {"local", "online"}:
            raise ValueError("Invalid model role or deployment")
        with self._connect() as connection:
            connection.execute(
                "UPDATE model_registry SET name=?, role=?, deployment=?, adapter=?, location=?, "
                "model_identifier=? WHERE id=?",
                (
                    name.strip(),
                    role,
                    deployment,
                    adapter,
                    location.strip(),
                    model_identifier.strip(),
                    model_id,
                ),
            )

    def set_chat_models(
        self, chat_id: str, language_model_id: str | None, decision_model_id: str | None
    ) -> None:
        with self._connect() as connection:
            account = connection.execute(
                "SELECT account_id FROM chats WHERE id=?", (chat_id,)
            ).fetchone()
            if account is None:
                raise ValueError("Chat does not exist")
            for model_id, role in (
                (language_model_id, "language"),
                (decision_model_id, "decision"),
            ):
                if model_id is None:
                    continue
                model = connection.execute(
                    "SELECT account_id, role FROM model_registry WHERE id=?", (model_id,)
                ).fetchone()
                if (
                    model is None
                    or model["role"] != role
                    or model["account_id"] != account["account_id"]
                ):
                    raise ValueError("Model must match the chat account and selected role")
            connection.execute(
                "INSERT INTO chat_models(chat_id, language_model_id, decision_model_id) "
                "VALUES (?, ?, ?) ON CONFLICT(chat_id) DO UPDATE SET "
                "language_model_id = excluded.language_model_id, "
                "decision_model_id = excluded.decision_model_id",
                (chat_id, language_model_id, decision_model_id),
            )

    def get_chat_models(self, chat_id: str) -> ChatModelSelection:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT language_model_id, decision_model_id FROM chat_models WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return ChatModelSelection(**dict(row)) if row else ChatModelSelection(None, None)

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
