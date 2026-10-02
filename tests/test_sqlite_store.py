"""Tests for versioned SQLite migrations and online backups."""

import sqlite3

import pytest

from core.sqlite_store import (
    SCHEMA_VERSION,
    backup_database,
    connect,
    current_schema_version,
    db_path_for,
    init_schema,
)


@pytest.fixture
def db_path(tmp_path):
    return db_path_for(tmp_path / "inventory.json")


def _prepare(db_path, rows=3):
    with connect(db_path) as conn:
        init_schema(conn)
        for i in range(rows):
            conn.execute(
                "INSERT INTO memories (texto, data) VALUES (?, ?)",
                (f"memoria {i}", "2025-01-01"),
            )


def test_init_schema_bootstraps_version(tmp_path):
    with connect(tmp_path / "x.json") as conn:
        assert current_schema_version(conn) == 0
        init_schema(conn)
        assert current_schema_version(conn) == SCHEMA_VERSION


def test_init_schema_is_idempotent(tmp_path):
    with connect(tmp_path / "x.json") as conn:
        init_schema(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"inventory_items", "inventory_movements", "memories"} <= tables
        init_schema(conn)
        assert current_schema_version(conn) == SCHEMA_VERSION


def test_memory_schema_includes_origin_columns(tmp_path):
    with connect(tmp_path / "y.json") as conn:
        init_schema(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memories)").fetchall()}
        assert {"origem", "conversation_id"} <= columns


def test_backup_database_creates_backup_file(db_path):
    _prepare(db_path)
    created = backup_database(db_path, keep=1)
    assert created is not None
    assert created.exists()
    with sqlite3.connect(str(created)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert count == 3


def test_backup_database_prunes_oldest(db_path):
    import os
    import time

    _prepare(db_path)
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    base = time.time()
    for days, name in (
        (10, "inventory-202501010-120000.db"),
        (8, "inventory-20250108-120000.db"),
        (5, "inventory-20250105-120000.db"),
    ):
        stale = backup_dir / name
        stale.write_bytes(b"stale")
        timestamp = base - days * 86400
        os.utime(stale, (timestamp, timestamp))
    created = backup_database(db_path, keep=2)
    assert created is not None
    names = {path.name for path in backup_dir.glob("*.db")}
    assert len(names) == 2
    assert "inventory-202501010-120000.db" not in names
    assert "inventory-20250105-120000.db" in names
    assert created.name in names


def test_backup_database_missing_returns_none(tmp_path):
    assert backup_database(db_path_for(tmp_path / "absent.json"), keep=1) is None
