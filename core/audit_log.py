"""Append-only local audit trail without request bodies or credentials."""

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
