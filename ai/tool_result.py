"""Structured tool execution results.

Replaces the opaque string returns from ``executar_ferramenta`` with a
typed result that preserves the old string for backward compatibility while
giving callers access to an error taxonomy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolErrorCode(Enum):
    """Why a tool call failed.  Stable keys for programmatic handling."""

    NOT_FOUND = "not_found"
    VALIDATION = "validation"
    CIRCUIT_OPEN = "circuit_open"
    CIRCUIT_OPENED = "circuit_opened"
    PERMISSION = "permission"
    EXECUTION = "execution"
    APPROVAL_REQUIRED = "approval_required"


@dataclass(frozen=True)
class ToolError:
    """A machine-readable description of a tool failure."""

    code: ToolErrorCode
    message: str
    tool: str
    #: Optional structured detail (e.g. which field failed validation)
    detail: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool call.  Either ``ok=True`` with ``data`` or ``ok=False`` with ``error``.

    ``str(result)`` returns the human message so existing code that does
    ``str(executar_ferramenta(...))`` continues to work unchanged.

    Also delegates common string methods to the string representation for
    backward compatibility with code that does ``result.startswith(...)`` etc.
    """

    ok: bool
    tool: str
    data: Any = None
    error: ToolError | None = None

    def __str__(self) -> str:
        if self.ok:
            return str(self.data) if self.data is not None else ""
        return str(self.error) if self.error else ""

    # Delegate string methods for backward compatibility
    def __getattr__(self, name: str):
        s = str(self)
        if hasattr(s, name):
            return getattr(s, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __contains__(self, item):
        return item in str(self)

    def __iter__(self):
        return iter(str(self))

    def __len__(self):
        return len(str(self))

    @staticmethod
    def success(tool: str, data: Any = None) -> ToolResult:
        return ToolResult(ok=True, tool=tool, data=data)

    @staticmethod
    def failure(
        tool: str,
        code: ToolErrorCode,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> ToolResult:
        return ToolResult(
            ok=False,
            tool=tool,
            error=ToolError(code=code, message=message, tool=tool, detail=detail),
        )


# ── Backward-compatible helpers ─────────────────────────────────


def _to_string_result(result: ToolResult | str) -> str:
    """Accept either the new type or a legacy string."""
    if isinstance(result, ToolResult):
        return str(result)
    return result


def _from_legacy_string(msg: str, tool: str) -> ToolResult:
    """Best-effort classification of an old-style error string.

    Used only during migration; not a substitute for real structured errors.
    """
    if not msg:
        return ToolResult.success(tool, msg)
    if msg.startswith("Ferramenta '") and msg.endswith("' nao encontrada."):
        return ToolResult.failure(tool, ToolErrorCode.NOT_FOUND, msg)
    if msg.startswith("Erro de validacao em '"):
        return ToolResult.failure(tool, ToolErrorCode.VALIDATION, msg)
    if "circuit breaker aberto" in msg or "indisponivel" in msg:
        return ToolResult.failure(tool, ToolErrorCode.CIRCUIT_OPEN, msg)
    if "AUTORIZAR" in msg or "APPROVAL_REQUIRED" in msg:
        return ToolResult.failure(tool, ToolErrorCode.APPROVAL_REQUIRED, msg)
    return ToolResult.failure(tool, ToolErrorCode.EXECUTION, msg)
