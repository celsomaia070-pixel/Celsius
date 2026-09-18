"""Shared SQLite persistence with automatic migration from legacy JSON.

Structured business data (inventory, long-term memory) is stored in SQLite so
writes are transactional and crash-safe. Legacy ``*.json`` files written by
older versions are migrated into the database on first access, keeping the
original files untouched for reference.

SQLite is already used for the vector index (``core/vector_store.py``); this
module provides the generic connection/schema helpers for business records.
"""

from __future__ import annotations

import datetime as _datetime
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from core.file_security import restrict_private_file

INVENTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory_items (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 0,
    estoque_min INTEGER NOT NULL DEFAULT 0,
    estoque_max INTEGER NOT NULL DEFAULT 0,
    localizacao TEXT NOT NULL DEFAULT 'em_estoque',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    item_nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    quantidade_anterior INTEGER NOT NULL,
    quantidade_nova INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
"""

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    texto TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT ''
);
"""

SCHEMAS: tuple[str, ...] = (INVENTORY_SCHEMA, MEMORY_SCHEMA)

#: Current schema version tracked in ``PRAGMA user_version``. Each target entry
#: runs only when the database is at an older version, so schema changes can be
#: shipped incrementally without dropping user data.
SCHEMA_VERSION = 2

_MEMORY_ORIGIN_MIGRATION = (
    "ALTER TABLE memories ADD COLUMN origem TEXT NOT NULL DEFAULT 'usuario';"
    "\nALTER TABLE memories ADD COLUMN conversation_id TEXT NOT NULL DEFAULT '';"
)

_MIGRATION_STEPS: tuple[tuple[int, str], ...] = (
    (1, INVENTORY_SCHEMA + MEMORY_SCHEMA),
    (2, _MEMORY_ORIGIN_MIGRATION),
)

_INVENTORY_ITEMS_EMPTY = "SELECT 1 FROM inventory_items LIMIT 1"
_MOVEMENTS_EMPTY = "SELECT 1 FROM inventory_movements LIMIT 1"
_MEMORIES_EMPTY = "SELECT 1 FROM memories LIMIT 1"

_INVENTORY_ITEM_INSERT = (
    "INSERT OR REPLACE INTO inventory_items "
    "(id, nome, categoria, quantidade, estoque_min, estoque_max, localizacao, "
    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_MOVEMENT_INSERT = (
    "INSERT OR REPLACE INTO inventory_movements "
    "(id, item_id, item_nome, tipo, quantidade, quantidade_anterior, "
    "quantidade_nova, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
_MEMORY_INSERT = "INSERT INTO memories (texto, data) VALUES (?, ?)"


def db_path_for(json_path: Path) -> Path:
    """Map a legacy JSON file path to its sibling SQLite database path."""
    return Path(json_path).with_suffix(".db")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open (creating if needed) a SQLite database with durable defaults.

    Writes inside the ``with`` block are committed atomically on normal exit
    and rolled back if any statement raises.
    """
    db_path = db_path_for(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    created = not db_path.exists()
    connection = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        if created:
            restrict_private_file(db_path)
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def current_schema_version(connection: sqlite3.Connection) -> int:
    """Return the ``PRAGMA user_version`` of the connected database."""
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def init_schema(connection: sqlite3.Connection) -> None:
    """Migrate the database schema up to :data:`SCHEMA_VERSION`.

    Runs idempotently: scripts use ``IF NOT EXISTS`` and ``user_version`` is
    bumped after every applied step, so re-opening an up-to-date database is a
    no-op.
    """
    version = current_schema_version(connection)
    for target, script in _MIGRATION_STEPS:
        if version < target:
            connection.executescript(script)
            connection.execute(f"PRAGMA user_version = {target}")
            version = target


DEFAULT_BACKUP_KEEP = 10


def backup_database(db_path: Path, *, keep: int = DEFAULT_BACKUP_KEEP) -> Path | None:
    """Copy a live SQLite database to ``backups/`` beside it.

    Uses the online backup API, so the copy is consistent even if another
    connection is writing. Old backups beyond *keep* are pruned (oldest first).
    Returns the backup path, or ``None`` when there is nothing to back up.
    """
    source = Path(db_path)
    if not source.exists():
        return None
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"{source.stem}-{stamp}.db"

    try:
        source_conn = sqlite3.connect(str(source))
        try:
            with suppress(sqlite3.OperationalError):
                source_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            destination_conn = sqlite3.connect(str(destination))
            try:
                source_conn.backup(destination_conn)
            finally:
                destination_conn.close()
        finally:
            source_conn.close()
    except sqlite3.Error:
        with suppress(OSError):
            destination.unlink(missing_ok=True)
        raise
    _prune_backups(backup_dir, keep)
    return destination


def _prune_backups(backup_dir: Path, keep: int) -> None:
    backups = sorted(
        backup_dir.glob("*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale in backups[keep:]:
        with suppress(OSError):
            stale.unlink(missing_ok=True)


def _has_rows(connection: sqlite3.Connection, check: str) -> bool:
    return connection.execute(check).fetchone() is not None


def migrate_inventory_json(json_path: Path, connection: sqlite3.Connection) -> bool:
    """Import legacy ``inventory.json`` data into an empty database."""
    path = Path(json_path)
    if not path.exists() or _has_rows(connection, _INVENTORY_ITEMS_EMPTY):
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False

    items = raw.get("items") or raw.get("itens", [])
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        connection.execute(
            _INVENTORY_ITEM_INSERT,
            (
                str(item.get("id") or ""),
                str(item.get("nome") or ""),
                str(item.get("categoria") or ""),
                int(item.get("quantidade") or 0),
                int(item.get("estoque_min") or 0),
                int(item.get("estoque_max") or 0),
                str(item.get("localizacao") or "em_estoque"),
                str(item.get("created_at") or ""),
                str(item.get("updated_at") or ""),
            ),
        )

    movements = raw.get("movimentacoes", [])
    for movement in movements if isinstance(movements, list) else []:
        if not isinstance(movement, dict):
            continue
        connection.execute(
            _MOVEMENT_INSERT,
            (
                str(movement.get("id") or ""),
                str(movement.get("item_id") or ""),
                str(movement.get("item_nome") or ""),
                str(movement.get("tipo") or ""),
                int(movement.get("quantidade") or 0),
                int(movement.get("quantidade_anterior") or 0),
                int(movement.get("quantidade_nova") or 0),
                str(movement.get("timestamp") or ""),
            ),
        )
    return True


def migrate_memories_json(json_path: Path, connection: sqlite3.Connection) -> bool:
    """Import legacy ``memorias.json`` entries into an empty database."""
    path = Path(json_path)
    if not path.exists() or _has_rows(connection, _MEMORIES_EMPTY):
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(raw, list):
        return False
    for memory in raw:
        if isinstance(memory, dict):
            connection.execute(
                _MEMORY_INSERT,
                (str(memory.get("texto") or ""), str(memory.get("data") or "")),
            )
        else:
            connection.execute(_MEMORY_INSERT, (str(memory), ""))
    return _has_rows(connection, _MEMORIES_EMPTY)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a :class:`sqlite3.Row` to a plain dict."""
    return dict(row)
