"""Durable, local-only schedules for supervised agent tasks."""

from __future__ import annotations

import builtins
import secrets
import time
from pathlib import Path
from typing import Any

from core.file_security import restrict_private_file
from core.json_persistence import atomic_write_json, locked_path, read_json

_MIN_INTERVAL_SECONDS = 60


class AgentScheduleStore:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "agent_schedules.json"

    def _read(self) -> list[dict[str, Any]]:
        data = read_json(self.path, [])
        return data if isinstance(data, list) else []

    def _write(self, values: list[dict[str, Any]]) -> None:
        atomic_write_json(self.path, values)
        restrict_private_file(self.path)

    def list(self, scope: str = "") -> list[dict[str, Any]]:
        with locked_path(self.path):
            values = self._read()
        if scope:
            values = [item for item in values if item.get("scope") == scope]
        return sorted(values, key=lambda item: float(item.get("next_run", 0)))

    def create(
        self, *, scope: str, objective: str, mode: str, every_seconds: int
    ) -> dict[str, Any]:
        if not scope or not objective.strip():
            raise ValueError("Conversa e objetivo sao obrigatorios.")
        every_seconds = max(_MIN_INTERVAL_SECONDS, min(int(every_seconds), 31_536_000))
        item = {
            "id": secrets.token_hex(6),
            "scope": scope,
            "objective": objective.strip(),
            "mode": mode,
            "every_seconds": every_seconds,
            "enabled": True,
            "next_run": time.time() + every_seconds,
            "last_run": 0.0,
            "last_error": "",
            "created": time.time(),
        }
        with locked_path(self.path):
            values = self._read()
            values.append(item)
            self._write(values)
        return item

    def set_enabled(self, schedule_id: str, scope: str, enabled: bool) -> dict[str, Any] | None:
        with locked_path(self.path):
            values = self._read()
            for item in values:
                if item.get("id") == schedule_id and item.get("scope") == scope:
                    item["enabled"] = enabled
                    self._write(values)
                    return item
        return None

    def due(self) -> builtins.list[dict[str, Any]]:
        now = time.time()
        with locked_path(self.path):
            values = self._read()
            due = []
            for item in values:
                if item.get("enabled") and float(item.get("next_run", 0)) <= now:
                    # Lease before dispatch: another process cannot dispatch the
                    # same schedule while this process submits it to the queue.
                    item["last_run"] = now
                    item["next_run"] = now + max(_MIN_INTERVAL_SECONDS, int(item["every_seconds"]))
                    due.append(dict(item))
            if due:
                self._write(values)
        return due

    def record_error(self, schedule_id: str, error: str) -> None:
        with locked_path(self.path):
            values = self._read()
            for item in values:
                if item.get("id") == schedule_id:
                    item["last_error"] = str(error)[:240]
                    break
            self._write(values)

    def record_dispatch(self, schedule_id: str, job_id: str) -> None:
        with locked_path(self.path):
            values = self._read()
            for item in values:
                if item.get("id") == schedule_id:
                    item["last_error"] = ""
                    item["last_job_id"] = str(job_id)
                    item["run_count"] = int(item.get("run_count", 0)) + 1
                    break
            self._write(values)

    def defer(self, schedule_id: str, error: str, *, retry_seconds: int = 30) -> None:
        """Release a failed dispatch lease for a near-term retry."""
        retry_at = time.time() + max(5, min(int(retry_seconds), _MIN_INTERVAL_SECONDS))
        with locked_path(self.path):
            values = self._read()
            for item in values:
                if item.get("id") == schedule_id:
                    item["last_error"] = str(error)[:240]
                    item["next_run"] = retry_at
                    break
            self._write(values)
