"""Persistent store for files the assistant produced, so the user can download them.

Incoming uploads are temporary: they are deleted as soon as the turn ends. That
is correct for user uploads, but useless for generated documents — a filled form
must still be downloadable from the conversation days later. This module keeps
those outputs in a separate directory that outlives the turn, and exposes them
through the same ``{id, name, size}`` shape the chat frontend already renders.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from core.chat_attachments import AttachmentError, StoredAttachment
from core.file_security import restrict_private_file
from core.file_validation import validate_file_content
from core.json_persistence import atomic_write_json

_VALID_ID = re.compile(r"^[a-f0-9]{32}$")

# Tools register their output through this while a chat turn is running. It stays
# None outside the web chat, so the desktop build simply produces no attachments.
_active_sink: ContextVar[_OutputSink | None] = ContextVar("celsius_output_sink", default=None)


@dataclass
class OutputAttachmentStore:
    """Keep generated files addressable by id after the turn that produced them."""

    root: Path
    allowed_extensions: set[str]
    max_bytes: int
    max_age_days: int = 30

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.prune()

    def register(self, path: str | Path, name: str = "") -> StoredAttachment:
        """Copy a generated file into the store and return its public handle."""

        source = Path(path).resolve()
        if not source.is_file():
            raise AttachmentError(f"Arquivo gerado nao encontrado: {source.name}")
        display = Path(name or source.name).name.strip() or source.name
        suffix = Path(display).suffix.lower()
        if suffix not in self.allowed_extensions:
            raise AttachmentError(f"Formato '{suffix or 'sem extensao'}' nao pode ser entregue.")
        size = source.stat().st_size
        if size > self.max_bytes:
            raise AttachmentError(
                f"O arquivo excede o limite local de {self.max_bytes // (1024 * 1024)} MB."
            )
        try:
            validate_file_content(display, source.read_bytes())
        except Exception as exc:  # noqa: BLE001 - surfaced as a delivery error
            raise AttachmentError(str(exc)) from exc

        attachment_id = uuid.uuid4().hex
        target = (self.root / f"{attachment_id}{suffix}").resolve()
        if target.parent != self.root:
            raise AttachmentError("Destino de arquivo invalido.")
        with self._lock:
            shutil.copyfile(source, target)
            restrict_private_file(target)
            # The display name lives beside the file so a download still works
            # after a restart, when the in-memory map is gone.
            atomic_write_json(self.root / f"{attachment_id}.json", {"name": display})
        return StoredAttachment(attachment_id, display, target, size)

    def get(self, attachment_id: str) -> StoredAttachment:
        if not _VALID_ID.fullmatch(attachment_id or ""):
            raise AttachmentError("Identificador de anexo invalido.")
        with self._lock:
            matches = [
                path
                for path in self.root.glob(f"{attachment_id}.*")
                if path.suffix.lower() != ".json"
            ]
            if not matches:
                raise AttachmentError("Arquivo nao encontrado ou expirado.")
            path = matches[0]
            name = path.name
            sidecar = self.root / f"{attachment_id}.json"
            if sidecar.is_file():
                try:
                    stored = json.loads(sidecar.read_text(encoding="utf-8"))
                    name = str(stored.get("name") or name)
                except (json.JSONDecodeError, OSError):
                    pass
            return StoredAttachment(attachment_id, name, path, path.stat().st_size)

    def prune(self) -> int:
        """Drop deliveries older than the retention window. Returns the count."""

        if self.max_age_days <= 0:
            return 0
        deadline = time.time() - (self.max_age_days * 86_400)
        removed = 0
        with self._lock:
            for path in self.root.iterdir():
                if not path.is_file():
                    continue
                try:
                    if path.stat().st_mtime < deadline:
                        path.unlink()
                        removed += 1
                except OSError:
                    continue
        return removed


@dataclass
class _OutputSink:
    """Links the store to the list that will be persisted on the message."""

    store: OutputAttachmentStore
    collected: list[dict[str, str | int]] = field(default_factory=list)


@contextmanager
def collect_outputs(store: OutputAttachmentStore):
    """Register generated files produced inside this block as chat attachments.

    Yields the list that will hold one public dict per delivered file. A tool
    that fails to register must not break the turn, so registration errors are
    swallowed and the file simply is not offered for download.
    """

    sink = _OutputSink(store=store, collected=[])
    token = _active_sink.set(sink)
    try:
        yield sink.collected
    finally:
        _active_sink.reset(token)


def output_delivery_active() -> bool:
    """Whether this turn must deliver generated files through chat attachments."""
    return _active_sink.get() is not None


def register_output(path: str | Path, name: str = "") -> StoredAttachment | None:
    """Offer a generated file to the user. No-op outside an active chat turn."""

    sink = _active_sink.get()
    if sink is None:
        return None
    try:
        stored = sink.store.register(path, name)
    except AttachmentError:
        return None
    sink.collected.append(stored.public_dict())
    return stored
