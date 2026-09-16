"""Best-effort owner-only permissions for locally persisted secrets."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


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
