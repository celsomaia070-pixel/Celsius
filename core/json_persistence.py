"""Small, dependency-free primitives for durable local JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}


def _process_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(resolved, threading.RLock())


@contextmanager
def locked_path(path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Lock a data path across threads and cooperating Celsius processes."""
    path = Path(path)
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with _process_lock(path), lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Tempo esgotado ao bloquear {path.name}") from None
                time.sleep(0.05)

        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_json(path: Path, default: Any) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON durably; callers should hold ``locked_path`` for transactions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
