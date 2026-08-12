"""Tests for the local document library and its web contracts."""

import time

import pytest
from fastapi.testclient import TestClient

from core.business_records import BusinessRecordService
from core.documents import DocumentLibraryError, DocumentLibraryService
from core.modules import MODULE_CHAT, MODULE_KNOWLEDGE, MODULE_SETTINGS
from core.settings import Settings
from core.web_api import EventHub, create_app


class FakeRAGService:
    def __init__(self):
        self.documents = {}

    def index_document(self, text, name, metadata=None):
        chunks = [part for part in text.split("\n\n") if part.strip()]
        self.documents[name] = {
            "text": text,
            "chunks": max(1, len(chunks)),
            "metadata": metadata or {},
        }
        return self.documents[name]["chunks"]

    def document_summaries(self):
        return [
            {
                "name": name,
                "chunk_count": item["chunks"],
                "char_count": len(item["text"]),
                "metadata": item["metadata"],
            }
            for name, item in self.documents.items()
        ]

    def search_context(self, query, top_k=5):
        query = query.casefold()
        return [
            f"[Fonte: {name}]\n{item['text']}"
            for name, item in self.documents.items()
            if query in item["text"].casefold()
        ][:top_k]

    def remove_document(self, name):
        removed = self.documents.pop(name, None)
        return "removido" if removed else "nao encontrado"


@pytest.fixture
def document_context(tmp_path):
    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.mobile.pairing_token = "document-token"
    settings.modules.set_enabled([MODULE_CHAT, MODULE_KNOWLEDGE, MODULE_SETTINGS])
    records = BusinessRecordService(
        data_file=tmp_path / "business_records.json",
        settings=settings,
    )
    rag = FakeRAGService()
    service = DocumentLibraryService(
        settings=settings,
        record_service=records,
        rag_service=rag,
        processor=lambda _path, **_kwargs: "politica comercial\n\nprazo de entrega em 5 dias",
    )
    yield settings, service, rag
    service.shutdown()


def _wait_for_job(service, job_id):
    for _attempt in range(100):
        job = service.get_job(job_id)
        if job["status"] in service.TERMINAL_JOB_STATUSES:
            return job
        time.sleep(0.01)
    raise AssertionError("A indexacao do documento nao terminou.")


def _headers():
    return {"Authorization": "Bearer document-token"}


class TestDocumentLibrary:
    def test_upload_indexes_and_persists_managed_document(self, document_context):
        _settings, service, _rag = document_context
        job, pending = service.submit_upload(
            "manual.txt",
            b"conteudo original",
            category="Operacao",
            responsible="Celso",
        )

        completed = _wait_for_job(service, job["id"])
        item = service.list_documents()[0]

        assert pending["status"] == "Processando"
        assert completed["status"] == "completed"
        assert item["status"] == "Indexado"
        assert item["chunk_count"] == 2
        assert item["category"] == "Operacao"
        assert item["file_available"] is True

    def test_existing_rag_document_remains_visible(self, document_context):
        _settings, service, rag = document_context
        rag.index_document("conteudo legado", "legado.pdf", {"category": "Historico"})

        item = service.list_documents()[0]

        assert item["filename"] == "legado.pdf"
        assert item["managed"] is False
        assert item["status"] == "Indexado"

    def test_rejects_unsupported_extension(self, document_context):
        _settings, service, _rag = document_context

        with pytest.raises(DocumentLibraryError, match="nao suportado"):
            service.submit_upload("programa.exe", b"binario")

    def test_reupload_updates_record_instead_of_creating_duplicate(self, document_context):
        _settings, service, _rag = document_context
        first_job, first = service.submit_upload("manual.txt", b"primeira versao")
        _wait_for_job(service, first_job["id"])
        second_job, second = service.submit_upload("manual.txt", b"segunda versao")
        _wait_for_job(service, second_job["id"])

        items = service.list_documents()
        path, _name = service.resolve_file(second["id"])

        assert first["id"] == second["id"]
        assert len(items) == 1
        assert path.read_bytes() == b"segunda versao"

    def test_search_and_delete_use_same_rag_base(self, document_context):
        _settings, service, rag = document_context
        job, _pending = service.submit_upload("manual.txt", b"arquivo")
        _wait_for_job(service, job["id"])
        item = service.list_documents()[0]

        results = service.search("prazo")
        deleted = service.delete(item["id"])

        assert "prazo de entrega" in results[0]
        assert deleted is True
        assert rag.documents == {}
        assert service.list_documents() == []


class TestWebDocuments:
    def test_document_endpoints_cover_upload_search_download_and_delete(self, document_context):
        settings, service, _rag = document_context
        app = create_app(
            settings=settings,
            event_hub=EventHub(),
            document_service=service,
        )
        with TestClient(app) as client:
            uploaded = client.post(
                "/api/v1/documents/upload",
                headers={
                    **_headers(),
                    "X-Celsius-Filename": "procedimento.txt",
                    "X-Celsius-Category": "Qualidade",
                },
                content=b"procedimento interno",
            )
            job_id = uploaded.json()["job"]["id"]
            for _attempt in range(100):
                job = client.get(
                    f"/api/v1/documents/jobs/{job_id}",
                    headers=_headers(),
                ).json()["job"]
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            listed = client.get("/api/v1/documents", headers=_headers())
            item = listed.json()["items"][0]
            searched = client.get(
                "/api/v1/documents/search",
                headers=_headers(),
                params={"query": "prazo"},
            )
            downloaded = client.get(
                f"/api/v1/documents/{item['id']}/file",
                headers=_headers(),
            )
            deleted = client.delete(
                f"/api/v1/documents/{item['id']}",
                headers=_headers(),
            )

        assert uploaded.status_code == 202
        assert job["status"] == "completed"
        assert item["category"] == "Qualidade"
        assert searched.json()["count"] == 1
        assert downloaded.content == b"procedimento interno"
        assert deleted.status_code == 200
