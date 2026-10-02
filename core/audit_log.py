"""Append-only local audit trail for task actions and security events."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.file_security import restrict_private_file


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.touch()
        restrict_private_file(self.path)

    @staticmethod
    def actor_fingerprint(credential: str) -> str:
        if not credential:
            return "anonymous"
        return hashlib.sha256(credential.encode("utf-8")).hexdigest()[:16]

    def record(
        self,
        *,
        method: str,
        path: str,
        status: int,
        actor: str,
        client: str,
    ) -> None:
        event = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "status": status,
            "actor": actor,
            "client": client,
        }
        payload = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def record_task_action(
        self,
        *,
        task_id: str,
        mode: str,
        user: str,
        step: int,
        tool: str,
        args_summary: str,
        jev_decision: str | None,
        policy_decision: str | None,
        confirmation: str | None,
        result: str,
        error: str | None = None,
        cancelled: bool = False,
    ) -> None:
        """Record a task action for audit purposes.

        Does not log secrets, tokens, or unnecessary sensitive content.
        """
        event = {
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "type": "task_action",
            "task_id": task_id,
            "mode": mode,
            "user": self.actor_fingerprint(user),
            "step": step,
            "tool": tool,
            "args_summary": args_summary[:240] if args_summary else "",
            "jev_decision": jev_decision,
            "policy_decision": policy_decision,
            "confirmation": confirmation,
            "result": "success"
            if not error and not cancelled
            else ("cancelled" if cancelled else "error"),
            "error": error[:240] if error else None,
            "cancelled": cancelled,
        }
        # Remove None values
        event = {k: v for k, v in event.items() if v is not None}
        payload = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
