"""Generate or validate the PEP 751 runtime dependency lock file."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "requirements.in"
LOCK = ROOT / "pylock.toml"
HASH_PREFIX = "# Celsius requirements.in sha256: "


def input_digest() -> str:
    return hashlib.sha256(INPUT.read_bytes()).hexdigest()


def check_lock() -> int:
    if not LOCK.exists():
        print("pylock.toml ausente. Execute: python tools/lock_requirements.py")
        return 1
    expected = f"{HASH_PREFIX}{input_digest()}"
    if expected not in LOCK.read_text(encoding="utf-8").splitlines()[:20]:
        print("pylock.toml desatualizado. Execute: python tools/lock_requirements.py")
        return 1
    return 0


def generate_lock() -> int:
    subprocess.run([sys.executable, str(ROOT / "tools" / "sync_requirements.py")], check=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "lock",
            "--requirement",
            str(INPUT),
            "--output",
            str(LOCK),
        ],
        cwd=ROOT,
        check=True,
    )
    content = LOCK.read_text(encoding="utf-8")
    LOCK.write_text(
        f"{HASH_PREFIX}{input_digest()}\n{content}",
        encoding="utf-8",
        newline="\n",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="fail when the lock is absent or stale"
    )
    args = parser.parse_args()
    return check_lock() if args.check else generate_lock()


if __name__ == "__main__":
    raise SystemExit(main())
