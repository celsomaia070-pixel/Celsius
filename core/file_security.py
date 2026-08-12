"""Best-effort owner-only permissions for locally persisted secrets."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def restrict_private_file(path: str | Path) -> None:
    target = Path(path)
    target.chmod(0o600)
    if os.name != "nt":
        return
    identity = subprocess.run(
        ["whoami"], capture_output=True, text=True, check=True, timeout=5
    ).stdout.strip()
    result = subprocess.run(
        ["icacls", str(target), "/inheritance:r", "/grant:r", f"{identity}:(R,W)"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise PermissionError(f"Nao foi possivel restringir {target.name}: {result.stderr.strip()}")
