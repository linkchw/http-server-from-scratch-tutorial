"""SQLite setup and a deliberately explicit repository layer."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with self.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in {0, SCHEMA_VERSION}:
                raise RuntimeError(
                    f"Database schema version {version} is not supported; "
                    f"expected {SCHEMA_VERSION}."
                )
            connection.execute("PRAGMA journal_mode = WAL")
            if version == 0:
                connection.executescript(schema)


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, values: Mapping[str, Any]) -> dict[str, Any]:
        columns = (
            "title",
            "description",
            "status",
            "priority",
            "due_date",
            "created_at",
            "updated_at",
        )
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks
                    (title, description, status, priority, due_date,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(values[column] for column in columns),
            )
            task_id = int(cursor.lastrowid)
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._task(row)

    def get(self, task_id: int) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._task(row) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        due_before: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if status:
            conditions.append("status = ?")
            parameters.append(status)
        if priority:
            conditions.append("priority = ?")
            parameters.append(priority)
        if due_before:
            conditions.append("due_date IS NOT NULL AND due_date <= ?")
            parameters.append(due_before)
        if search:
            conditions.append("(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            needle = f"%{escaped}%"
            parameters.extend((needle, needle))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    "SELECT count(*) FROM tasks" + where,
                    parameters,
                ).fetchone()[0]
            )
            rows = connection.execute(
                "SELECT * FROM tasks"
                + where
                + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        return [self._task(row) for row in rows], total

    def replace(self, task_id: int, values: Mapping[str, Any]) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET title = ?, description = ?, status = ?, priority = ?,
                    due_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["title"],
                    values["description"],
                    values["status"],
                    values["priority"],
                    values["due_date"],
                    values["updated_at"],
                    task_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._task(row)

    def update(self, task_id: int, values: Mapping[str, Any]) -> dict[str, Any] | None:
        allowed = {"title", "description", "status", "priority", "due_date", "updated_at"}
        selected = {name: value for name, value in values.items() if name in allowed}
        assignments = ", ".join(f"{name} = ?" for name in selected)
        parameters = [*selected.values(), task_id]
        with self.database.connect() as connection:
            cursor = connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?",
                parameters,
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._task(row)

    def delete(self, task_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return cursor.rowcount > 0

    @staticmethod
    def _task(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "title": str(row["title"]),
            "description": str(row["description"]),
            "status": str(row["status"]),
            "priority": str(row["priority"]),
            "due_date": row["due_date"],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

