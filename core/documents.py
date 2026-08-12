"""Local document library shared by the web UI, desktop tools and RAG."""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.business_records import BusinessRecord, BusinessRecordService, get_business_record_service
from core.modules import MODULE_KNOWLEDGE
from core.settings import get_settings


class DocumentLibraryError(ValueError):
    """Raised when a document cannot be accepted or managed safely."""


@dataclass
class DocumentJob:
    id: str
    document_id: str
    status: str = "queued"
    error: str = ""

    def public_dict(self) -> dict[str, str]:
        return asdict(self)


class DocumentLibraryService:
    """Persist source files and coordinate extraction plus local RAG indexing."""

    TERMINAL_JOB_STATUSES = {"completed", "failed"}

    def __init__(
        self,
        *,
        settings=None,
        record_service: BusinessRecordService | None = None,
        rag_service=None,
        event_hub=None,
        processor: Callable | None = None,
    ):
        self.settings = settings or get_settings()
        self.record_service = record_service or (
            get_business_record_service()
            if self.settings is get_settings()
            else BusinessRecordService(settings=self.settings)
        )
        self._rag_service = rag_service
        self.event_hub = event_hub
        self._processor = processor
        self.storage_dir = (Path(self.settings.data_dir) / "documents" / "files").resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.allowed_extensions = {extension.lower() for extension in self.settings.doc_extensions}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CelsiusDocuments")
        self._jobs: dict[str, DocumentJob] = {}
        self._lock = threading.RLock()

    @property
    def rag_service(self):
        if self._rag_service is None:
            from ai.rag import RAGService, get_rag_service

            self._rag_service = (
                get_rag_service()
                if self.settings is get_settings()
                else RAGService(settings=self.settings)
            )
        return self._rag_service

    def max_bytes_for(self, filename: str) -> int:
        suffix = Path(filename).suffix.lower()
        limit_mb = (
            self.settings.file.max_pdf_size_mb
            if suffix == ".pdf"
            else self.settings.max_file_size_mb
        )
        return max(1, int(limit_mb)) * 1024 * 1024

    def _validate_upload(self, filename: str, content: bytes) -> tuple[str, str]:
        clean_name = Path(filename or "").name.strip()
        if not clean_name or clean_name in {".", ".."}:
            raise DocumentLibraryError("Nome de arquivo invalido.")
        suffix = Path(clean_name).suffix.lower()
        if suffix not in self.allowed_extensions:
            raise DocumentLibraryError(f"Formato '{suffix or 'sem extensao'}' nao suportado.")
        if not content:
            raise DocumentLibraryError("O arquivo enviado esta vazio.")
        if len(content) > self.max_bytes_for(clean_name):
            limit = self.max_bytes_for(clean_name) // (1024 * 1024)
            raise DocumentLibraryError(f"O arquivo excede o limite local de {limit} MB.")
        return clean_name, suffix

    def _create_pending_record(
        self,
        filename: str,
        content: bytes,
        *,
        title: str = "",
        document_type: str = "Outro",
        category: str = "",
        origin: str = "",
        responsible: str = "",
    ) -> BusinessRecord:
        clean_name, suffix = self._validate_upload(filename, content)
        stored_path = (self.storage_dir / f"{uuid.uuid4().hex}{suffix}").resolve()
        if stored_path.parent != self.storage_dir:
            raise DocumentLibraryError("Destino do documento invalido.")
        temporary_path = stored_path.with_suffix(f"{stored_path.suffix}.tmp")
        temporary_path.write_bytes(content)
        os.replace(temporary_path, stored_path)
        fields = {
            "titulo": (title or Path(clean_name).stem).strip(),
            "tipo": document_type.strip() or "Outro",
            "origem": origin.strip(),
            "categoria": category.strip(),
            "responsavel": responsible.strip(),
            "status": "Processando",
            "observacoes": "",
            "nome_arquivo": clean_name,
            "arquivo_local": stored_path.name,
            "tamanho_bytes": str(len(content)),
            "criado_em": datetime.now().isoformat(timespec="minutes"),
        }
        existing = next(
            (
                record
                for record in self.record_service.list_by_module(MODULE_KNOWLEDGE)
                if record.fields.get("nome_arquivo", "").casefold() == clean_name.casefold()
            ),
            None,
        )
        old_path = self._record_path(existing) if existing is not None else None
        try:
            record = self.record_service.save_record(
                MODULE_KNOWLEDGE,
                fields["titulo"],
                fields,
                record_id=existing.id if existing is not None else "",
            )
            if old_path is not None and old_path != stored_path:
                old_path.unlink(missing_ok=True)
            return record
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise

    def submit_upload(self, filename: str, content: bytes, **metadata) -> tuple[dict, dict]:
        record = self._create_pending_record(filename, content, **metadata)
        job = DocumentJob(id=uuid.uuid4().hex, document_id=record.id)
        with self._lock:
            self._jobs[job.id] = job
        self._publish("documents.changed", {"action": "created", "document": self._item(record)})
        self._executor.submit(self._run_job, job.id)
        return job.public_dict(), self._item(record)

    def import_path(self, path: Path, **metadata) -> dict:
        path = Path(path).resolve()
        record = self._create_pending_record(path.name, path.read_bytes(), **metadata)
        try:
            self._process_record(record.id)
        except Exception as exc:
            self._mark_failed(record.id, str(exc))
            raise
        refreshed = self.record_service.get(record.id)
        return self._item(refreshed or record)

    def submit_reindex(self, document_id: str) -> dict:
        record = self._managed_record(document_id)
        path = self._record_path(record)
        if path is None or not path.is_file():
            raise DocumentLibraryError("O arquivo local deste documento nao esta disponivel.")
        fields = dict(record.fields)
        fields["status"] = "Processando"
        fields.pop("erro_indexacao", None)
        self.record_service.save_record(
            MODULE_KNOWLEDGE,
            record.title,
            fields,
            record_id=record.id,
        )
        job = DocumentJob(id=uuid.uuid4().hex, document_id=record.id)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run_job, job.id)
        self._publish("documents.changed", {"action": "reindexing", "document_id": record.id})
        return job.public_dict()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "processing"
        self._publish("documents.job", {"job": job.public_dict()})
        try:
            self._process_record(job.document_id)
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
            self._mark_failed(job.document_id, str(exc))
        else:
            with self._lock:
                job.status = "completed"
        self._publish("documents.job", {"job": job.public_dict()})
        record = self.record_service.get(job.document_id)
        if record:
            self._publish(
                "documents.changed", {"action": job.status, "document": self._item(record)}
            )

    def _process_record(self, document_id: str) -> None:
        record = self._managed_record(document_id)
        path = self._record_path(record)
        if path is None or not path.is_file():
            raise DocumentLibraryError("Arquivo local nao encontrado.")
        if self._processor is None:
            from processors import processar_arquivo

            processor = processar_arquivo
        else:
            processor = self._processor
        text = str(processor(str(path), base_dir=path.parent)).strip()
        if len(text) < 10 or text.lower().startswith(("erro", "formato '")):
            raise DocumentLibraryError(text or "Nenhum texto util foi extraido do documento.")
        fields = dict(record.fields)
        original_name = fields.get("nome_arquivo", record.title)
        chunks = self.rag_service.index_document(
            text,
            original_name,
            {
                "record_id": record.id,
                "category": fields.get("categoria", ""),
                "document_type": fields.get("tipo", "Outro"),
                "origin": fields.get("origem", ""),
            },
        )
        if chunks <= 0:
            raise DocumentLibraryError("Nao foi possivel criar trechos pesquisaveis.")
        fields.update(
            {
                "status": "Indexado",
                "quantidade_trechos": str(chunks),
                "caracteres_extraidos": str(len(text)),
                "indexado_em": datetime.now().isoformat(timespec="minutes"),
                "erro_indexacao": "",
            }
        )
        self.record_service.save_record(
            MODULE_KNOWLEDGE,
            record.title,
            fields,
            record_id=record.id,
        )

    def _mark_failed(self, document_id: str, error: str) -> None:
        record = self.record_service.get(document_id)
        if record is None:
            return
        fields = dict(record.fields)
        fields["status"] = "Revisar"
        fields["erro_indexacao"] = error[:500]
        self.record_service.save_record(
            MODULE_KNOWLEDGE,
            record.title,
            fields,
            record_id=record.id,
        )

    def get_job(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise DocumentLibraryError("Processamento de documento nao encontrado.")
            return job.public_dict()

    def list_documents(self) -> list[dict[str, Any]]:
        summaries = {item["name"]: item for item in self.rag_service.document_summaries()}
        items = []
        managed_names = set()
        for record in self.record_service.list_by_module(MODULE_KNOWLEDGE):
            name = record.fields.get("nome_arquivo", record.title)
            managed_names.add(name)
            items.append(self._item(record, summaries.get(name)))
        for name, summary in summaries.items():
            if name in managed_names:
                continue
            items.append(
                {
                    "id": self._rag_id(name),
                    "title": name,
                    "filename": name,
                    "document_type": summary["metadata"].get("document_type", "Outro"),
                    "category": summary["metadata"].get("category", ""),
                    "origin": summary["metadata"].get("origin", "Indice local"),
                    "responsible": "",
                    "status": "Indexado",
                    "chunk_count": summary["chunk_count"],
                    "char_count": summary["char_count"],
                    "size": 0,
                    "updated_at": "",
                    "error": "",
                    "managed": False,
                    "file_available": False,
                }
            )
        return sorted(
            items, key=lambda item: (item["status"] != "Processando", item["title"].casefold())
        )

    def _item(self, record: BusinessRecord, summary: dict | None = None) -> dict[str, Any]:
        fields = record.fields
        path = self._record_path(record)
        return {
            "id": record.id,
            "title": record.title,
            "filename": fields.get("nome_arquivo", record.title),
            "document_type": fields.get("tipo", "Outro"),
            "category": fields.get("categoria", ""),
            "origin": fields.get("origem", ""),
            "responsible": fields.get("responsavel", ""),
            "status": fields.get("status", "Pendente"),
            "chunk_count": int(fields.get("quantidade_trechos", "0") or 0)
            or int((summary or {}).get("chunk_count", 0)),
            "char_count": int(fields.get("caracteres_extraidos", "0") or 0)
            or int((summary or {}).get("char_count", 0)),
            "size": int(fields.get("tamanho_bytes", "0") or 0),
            "updated_at": fields.get("indexado_em", record.updated_at),
            "error": fields.get("erro_indexacao", ""),
            "managed": True,
            "file_available": bool(path and path.is_file()),
        }

    def search(self, query: str, *, top_k: int = 5) -> list[str]:
        clean_query = query.strip()
        if not clean_query:
            raise DocumentLibraryError("Informe o que deseja pesquisar.")
        return self.rag_service.search_context(clean_query, top_k=max(1, min(top_k, 12)))

    def delete(self, document_id: str) -> bool:
        record = self.record_service.get(document_id)
        if record is not None and record.module_id == MODULE_KNOWLEDGE:
            name = record.fields.get("nome_arquivo", record.title)
            self.rag_service.remove_document(name)
            path = self._record_path(record)
            if path:
                path.unlink(missing_ok=True)
            self.record_service.delete(record.id)
            self._publish("documents.changed", {"action": "deleted", "document_id": document_id})
            return True
        for summary in self.rag_service.document_summaries():
            if self._rag_id(summary["name"]) == document_id:
                self.rag_service.remove_document(summary["name"])
                self._publish(
                    "documents.changed", {"action": "deleted", "document_id": document_id}
                )
                return True
        return False

    def delete_by_name(self, document_name: str) -> bool:
        wanted = document_name.strip().casefold()
        for item in self.list_documents():
            if item["filename"].casefold() == wanted or item["title"].casefold() == wanted:
                return self.delete(item["id"])
        return False

    def resolve_file(self, document_id: str) -> tuple[Path, str]:
        record = self._managed_record(document_id)
        path = self._record_path(record)
        if path is None or not path.is_file():
            raise DocumentLibraryError("Arquivo local nao disponivel.")
        return path, record.fields.get("nome_arquivo", record.title)

    def list_text(self) -> str:
        items = self.list_documents()
        if not items:
            return "Nenhum documento indexado."
        lines = [f"Documentos locais ({len(items)}):"]
        lines.extend(
            f"- {item['title']} | {item['status']} | {item['chunk_count']} trechos"
            for item in items
        )
        return "\n".join(lines)

    def _managed_record(self, document_id: str) -> BusinessRecord:
        record = self.record_service.get(document_id)
        if record is None or record.module_id != MODULE_KNOWLEDGE:
            raise DocumentLibraryError("Documento nao encontrado.")
        return record

    def _record_path(self, record: BusinessRecord) -> Path | None:
        filename = record.fields.get("arquivo_local", "")
        if not filename:
            return None
        path = (self.storage_dir / Path(filename).name).resolve()
        return path if path.parent == self.storage_dir else None

    @staticmethod
    def _rag_id(name: str) -> str:
        return f"rag-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:12]}"

    def _publish(self, event_type: str, payload: dict) -> None:
        if self.event_hub is not None:
            self.event_hub.publish(event_type, payload)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)


_document_library_service: DocumentLibraryService | None = None
_document_library_lock = threading.Lock()


def get_document_library_service() -> DocumentLibraryService:
    global _document_library_service
    if _document_library_service is None:
        with _document_library_lock:
            if _document_library_service is None:
                _document_library_service = DocumentLibraryService()
    return _document_library_service


def reset_document_library_service() -> None:
    global _document_library_service
    if _document_library_service is not None:
        _document_library_service.shutdown()
    _document_library_service = None
