"""Small local vector store backed by SQLite and cosine distance."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

import numpy as np

from core.file_security import restrict_private_file


class LocalVectorCollection:
    """Subset of the collection API needed by Celsius RAG."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    dimensions INTEGER NOT NULL
                )
                """
            )
        restrict_private_file(self.path)

    def count(self) -> int:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM vectors").fetchone()
        return int(row[0]) if row else 0

    def add(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not (len(ids) == len(embeddings) == len(documents) == len(metadatas)):
            raise ValueError("Dados vetoriais com tamanhos incompativeis.")
        rows = []
        for item_id, embedding, document, metadata in zip(
            ids, embeddings, documents, metadatas, strict=True
        ):
            vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
            if not vector.size or not np.isfinite(vector).all():
                raise ValueError("Embedding invalido.")
            rows.append(
                (
                    item_id,
                    document,
                    json.dumps(metadata, ensure_ascii=False),
                    vector.tobytes(),
                    int(vector.size),
                )
            )
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO vectors (id, document, metadata, embedding, dimensions)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    document=excluded.document,
                    metadata=excluded.metadata,
                    embedding=excluded.embedding,
                    dimensions=excluded.dimensions
                """,
                rows,
            )

    def get(self, where: dict[str, Any] | None = None) -> dict[str, list[Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, document, metadata FROM vectors ORDER BY id"
            ).fetchall()
        result = {"ids": [], "documents": [], "metadatas": []}
        for item_id, document, metadata_json in rows:
            metadata = json.loads(metadata_json)
            if where and any(metadata.get(key) != value for key, value in where.items()):
                continue
            result["ids"].append(item_id)
            result["documents"].append(document)
            result["metadatas"].append(metadata)
        return result

    def delete(self, *, ids: list[str]) -> None:
        if not ids:
            return
        with self._lock, self._connect() as connection:
            connection.executemany(
                "DELETE FROM vectors WHERE id = ?", ((item_id,) for item_id in ids)
            )

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
    ) -> dict[str, list[list[Any]]]:
        if not query_embeddings or n_results <= 0:
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}
        query = np.asarray(query_embeddings[0], dtype=np.float32).reshape(-1)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT id, document, metadata, embedding, dimensions FROM vectors"
            ).fetchall()

        ranked: list[tuple[float, str, str, dict[str, Any]]] = []
        query_norm = float(np.linalg.norm(query))
        for item_id, document, metadata_json, blob, dimensions in rows:
            if dimensions != query.size:
                continue
            vector = np.frombuffer(blob, dtype=np.float32, count=dimensions)
            denominator = query_norm * float(np.linalg.norm(vector))
            similarity = float(np.dot(query, vector) / denominator) if denominator else 0.0
            distance = 1.0 - max(-1.0, min(1.0, similarity))
            ranked.append((distance, item_id, document, json.loads(metadata_json)))
        ranked.sort(key=lambda item: item[0])
        selected = ranked[:n_results]
        return {
            "ids": [[item[1] for item in selected]],
            "documents": [[item[2] for item in selected]],
            "distances": [[item[0] for item in selected]],
            "metadatas": [[item[3] for item in selected]],
        }
