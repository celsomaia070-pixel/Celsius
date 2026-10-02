"""Durable checkpoints for local agent tasks, separate from conversation memory."""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from core.agent_modes import DEFAULT_MODE_ID, get_mode, is_valid_mode
from core.sqlite_store import connect

# ── Task lifecycle ──────────────────────────────────────────
#
# One vocabulary, used by the store, the runtime, the API and the UI, so a task
# cannot be "running" in one surface and "paused" in another.
#
#   created             -> accepted, nothing executed yet
#   planning            -> building the step list
#   waiting_confirmation-> a step needs an explicit human decision
#   running             -> at least one tool call is in flight
#   paused              -> stopped on purpose (user, budget or ambiguity)
#   cancelled           -> the user called it off; never resumed
#   failed              -> an error the user has to resolve
#   completed           -> finished with a result

TASK_STATES: tuple[str, ...] = (
    "created",
    "planning",
    "waiting_confirmation",
    "running",
    "paused",
    "cancelled",
    "failed",
    "completed",
)

#: States from which no further work happens.
TERMINAL_STATES: frozenset[str] = frozenset({"cancelled", "failed", "completed"})

#: States a user may resume from. ``failed`` is deliberately absent: a task that
#: hit a budget or an unrecoverable error stays final until the user starts a new
#: one, so a spent budget can never be replayed by a stray RETOMAR.
RESUMABLE_STATES: frozenset[str] = frozenset({"paused", "waiting_confirmation", "cancelled"})

#: Legacy statuses still present in checkpoints written by older builds.
_LEGACY_STATES: dict[str, str] = {
    "awaiting_approval": "waiting_confirmation",
    "needs_review": "paused",
    "blocked": "paused",
    "planning": "planning",
    "running": "running",
    "paused": "paused",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
    "created": "created",
}


def normalize_state(state: str) -> str:
    """Map any historical/legacy status onto the current vocabulary."""
    key = str(state or "").strip().lower()
    if key in TASK_STATES:
        return key
    return _LEGACY_STATES.get(key, "paused")


def is_terminal(state: str) -> bool:
    return normalize_state(state) in TERMINAL_STATES


def is_resumable(state: str) -> bool:
    return normalize_state(state) in RESUMABLE_STATES


class AgentTaskStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        with connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS agent_tasks ("
                "id TEXT PRIMARY KEY, scope TEXT NOT NULL, updated REAL NOT NULL, "
                "checkpoint TEXT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS agent_tasks_scope ON agent_tasks(scope, updated)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS agent_preferences ("
                "scope TEXT PRIMARY KEY, mode TEXT NOT NULL, updated REAL NOT NULL)"
            )

    def set_mode(self, scope: str, mode: str) -> str:
        if not scope:
            raise ValueError("Uma conversa e obrigatoria.")
        resolved = get_mode(mode if is_valid_mode(mode) else DEFAULT_MODE_ID).id
        with connect(self.path) as db:
            db.execute(
                "INSERT INTO agent_preferences(scope, mode, updated) VALUES (?, ?, ?) "
                "ON CONFLICT(scope) DO UPDATE SET mode=excluded.mode, updated=excluded.updated",
                (scope, resolved, time.time()),
            )
        return resolved

    def get_stored_mode(self, scope: str) -> str | None:
        with connect(self.path) as db:
            row = db.execute(
                "SELECT mode FROM agent_preferences WHERE scope=?", (scope,)
            ).fetchone()
        return get_mode(row["mode"]).id if row else None

    def get_mode(self, scope: str) -> str:
        return self.get_stored_mode(scope) or DEFAULT_MODE_ID

    def create(self, scope: str, prompt: dict[str, Any], *, mode: str = "") -> dict[str, Any]:
        if not scope:
            raise ValueError("Uma tarefa precisa estar vinculada a uma conversa.")
        resolved_mode = mode if is_valid_mode(mode) else get_mode(mode or DEFAULT_MODE_ID).id
        task = {
            "id": secrets.token_hex(6),
            "scope": scope,
            "status": "created",
            "mode": resolved_mode,
            "objective": prompt["pergunta"],
            "prompt": prompt,
            "messages": [],
            "steps": [],
            "plan": [],
            "iterations": 0,
            "result": "",
            "error": "",
            "workspace": "",
            "verification": {},
            "created": time.time(),
            "updated": time.time(),
        }
        from core.agent_artifacts import workspace_for

        task["workspace"] = str(workspace_for(self.path.parent, task["id"]))
        with connect(self.path) as db:
            db.execute(
                "INSERT INTO agent_tasks VALUES (?, ?, ?, ?)",
                (task["id"], scope, task["updated"], json.dumps(task, ensure_ascii=False)),
            )
        return task

    def save(self, task: dict[str, Any]) -> None:
        task["status"] = normalize_state(task.get("status", "paused"))
        task["updated"] = time.time()
        with connect(self.path) as db:
            db.execute(
                "UPDATE agent_tasks SET updated=?, checkpoint=? WHERE id=? AND scope=?",
                (task["updated"], json.dumps(task, ensure_ascii=False), task["id"], task["scope"]),
            )

    def get(self, task_id: str, scope: str) -> dict[str, Any] | None:
        with connect(self.path) as db:
            row = db.execute(
                "SELECT checkpoint FROM agent_tasks WHERE id=? AND scope=?",
                (task_id.lower(), scope),
            ).fetchone()
        if not row:
            return None
        task = json.loads(row[0])
        # Reading is also a migration point: legacy statuses are normalized on
        # load so no caller has to deal with two vocabularies.
        task["status"] = normalize_state(task.get("status", "paused"))
        return task

    def list(self, scope: str, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT checkpoint FROM agent_tasks WHERE scope=? ORDER BY updated DESC LIMIT ?",
                (scope, min(max(limit, 1), 200)),
            ).fetchall()
        tasks = []
        for row in rows:
            task = json.loads(row[0])
            task["status"] = normalize_state(task.get("status", "paused"))
            tasks.append(task)
        return tasks

    def find_approval(self, code: str, scope: str) -> dict[str, Any] | None:
        # Do not limit this lookup to the last page of tasks.
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT checkpoint FROM agent_tasks WHERE scope=?", (scope,)
            ).fetchall()
        for row in rows:
            task = json.loads(row[0])
            if normalize_state(task.get("status", "")) == "waiting_confirmation" and any(
                step.get("approval_code") == code.upper() for step in task["steps"]
            ):
                return task
        return None
