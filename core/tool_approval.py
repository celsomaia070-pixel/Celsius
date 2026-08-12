"""One-time, user-mediated approvals for sensitive assistant tools."""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

APPROVAL_REQUIRED_PREFIX = "__CELSIUS_APPROVAL_REQUIRED__"
SENSITIVE_TOOLS = frozenset({"executar_codigo", "navegar_web", "remover_documento"})
_COMMAND = re.compile(r"^\s*(AUTORIZAR|CANCELAR)\s+([A-Z0-9]{6,12})\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PendingToolApproval:
    code: str
    tool: str
    arguments: dict[str, Any]
    created_at: float


class ToolApprovalStore:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._pending: dict[str, PendingToolApproval] = {}
        self._lock = threading.RLock()

    def request(self, tool: str, arguments: dict[str, Any]) -> PendingToolApproval:
        with self._lock:
            self._purge()
            code = secrets.token_hex(4).upper()
            request = PendingToolApproval(code, tool, dict(arguments), time.monotonic())
            self._pending[code] = request
            return request

    def parse_command(self, text: str) -> tuple[str, str] | None:
        match = _COMMAND.fullmatch(text or "")
        if not match:
            return None
        return match.group(1).upper(), match.group(2).upper()

    def consume(self, code: str) -> PendingToolApproval | None:
        with self._lock:
            self._purge()
            return self._pending.pop(code.upper(), None)

    def cancel(self, code: str) -> bool:
        return self.consume(code) is not None

    def _purge(self) -> None:
        cutoff = time.monotonic() - self.ttl_seconds
        expired = [code for code, item in self._pending.items() if item.created_at < cutoff]
        for code in expired:
            self._pending.pop(code, None)


def approval_message(request: PendingToolApproval) -> str:
    preview = json.dumps(request.arguments, ensure_ascii=False, indent=2)
    if len(preview) > 1800:
        preview = f"{preview[:1800]}\n... [conteudo truncado]"
    return (
        f"{APPROVAL_REQUIRED_PREFIX}\n"
        "Esta acao exige sua aprovacao explicita porque pode alterar dados, acessar a internet "
        "ou executar codigo local.\n\n"
        f"Ferramenta: {request.tool}\n"
        f"Argumentos propostos:\n```json\n{preview}\n```\n\n"
        f"Para executar exatamente esta acao, envie: AUTORIZAR {request.code}\n"
        f"Para descartar, envie: CANCELAR {request.code}\n"
        "A autorizacao expira em 5 minutos."
    )


_STORE = ToolApprovalStore()


def get_tool_approval_store() -> ToolApprovalStore:
    return _STORE
