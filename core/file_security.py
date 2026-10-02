"""File security: path validation, allowed roots, and write confirmation."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# Global allowed roots for file operations
_allowed_roots: list[Path] = []


def set_allowed_roots(roots: list[str | Path]) -> None:
    """Set the allowed root directories for file operations."""
    global _allowed_roots
    _allowed_roots = [Path(r).resolve() for r in roots if r]


def get_allowed_roots() -> list[Path]:
    """Get the currently configured allowed roots."""
    return list(_allowed_roots)


def validate_managed_path(path: str | Path, *, data_root: Path) -> Path:
    """Validate fixed application storage under its configured data root.

    This does not change the roots available to agent file tools. The root must
    come from application settings, never from a tool or user-supplied path.
    """
    target = Path(path).resolve()
    try:
        target.relative_to(Path(data_root).resolve())
    except ValueError as exc:
        raise PermissionError("Caminho fora da pasta de dados da aplicação.") from exc
    return target


def validate_path(path: str | Path, *, allow_create: bool = False) -> Path:
    """Validate that a path is within allowed roots and not a traversal attempt.

    Args:
        path: The path to validate.
        allow_create: If True, allow the path even if it doesn't exist yet (for creation).

    Returns:
        The resolved absolute path.

    Raises:
        PermissionError: If path is outside allowed roots or contains traversal.
        FileNotFoundError: If path doesn't exist and allow_create is False.
    """
    target = Path(path).resolve()

    # Check for path traversal attempts
    try:
        target.relative_to(target.anchor)
    except ValueError as exc:
        raise PermissionError(f"Caminho inválido (travessia detectada): {path}") from exc

    # Check against allowed roots
    if not _allowed_roots:
        # If no roots configured, allow only within current working directory
        cwd = Path.cwd().resolve()
        try:
            target.relative_to(cwd)
        except ValueError as exc:
            raise PermissionError(f"Caminho fora do diretório permitido: {path}") from exc
    else:
        allowed = False
        for root in _allowed_roots:
            try:
                target.relative_to(root)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            roots_str = ", ".join(str(r) for r in _allowed_roots)
            raise PermissionError(f"Caminho fora das raízes permitidas ({roots_str}): {path}")

    # Check existence
    if not allow_create and not target.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    return target


def require_write_confirmation(path: str | Path, operation: str = "escrever") -> bool:
    """Check if a write operation requires explicit user confirmation.

    This is a policy function - the actual confirmation UI is handled by the caller.
    """
    # All write operations require confirmation by default
    return True


def restrict_private_file(path: str | Path) -> bool:
    """Restrict a private file when the operating system permits it.

    Local persistence must remain available even on managed Windows machines
    where account-name to SID resolution is unavailable.  Failing closed here
    would prevent the whole application from opening, so callers receive a
    boolean and the failure is recorded for diagnosis instead.
    """

    target = Path(path)
    try:
        target.chmod(0o600)
    except OSError as exc:
        logger.warning("Could not set basic private permissions on %s: %s", target.name, exc)
        return False

    if os.name != "nt":
        return True

    try:
        identity = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        ).stdout.strip()
        if not identity:
            raise OSError("Windows did not return the current account identity")
        result = subprocess.run(
            ["icacls", str(target), "/inheritance:r", "/grant:r", f"{identity}:(R,W)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("Could not restrict %s with Windows ACLs: %s", target.name, exc)
        return False

    if result.returncode != 0:
        logger.warning(
            "Could not restrict %s with Windows ACLs: %s",
            target.name,
            result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}",
        )
        return False
    return True


def restrict_private_directory(path: str | Path) -> bool:
    """Create a directory and restrict new and existing children to this account."""
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    try:
        target.chmod(0o700)
    except OSError as exc:
        logger.warning("Could not set private directory permissions on %s: %s", target.name, exc)
        return False
    if os.name != "nt":
        return True
    try:
        identity = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=5,
        ).stdout.strip()
        if not identity:
            raise OSError("Windows did not return the current account identity")
        # "/T" must not be used here. Recursing applies "/inheritance:r" to child
        # files, but "(OI)(CI)F" only applies to directories, so icacls strips every
        # inherited ACE from those files and grants them nothing back, leaving files
        # that no account can read. The inheritable ACE below already covers children.
        result = subprocess.run(
            [
                "icacls",
                str(target),
                "/inheritance:r",
                "/grant:r",
                f"{identity}:(OI)(CI)F",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("Could not restrict directory %s with Windows ACLs: %s", target.name, exc)
        return False
    if result.returncode != 0:
        logger.warning(
            "Could not restrict directory %s with Windows ACLs: %s",
            target.name,
            result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}",
        )
        return False
    return True
