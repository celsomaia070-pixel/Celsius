"""Measure real local reports and public news retrieval without sending WhatsApp messages.

Uses a read-only inventory snapshot, isolated output storage and the real tools.
Only counts, flags and timings are persisted, never inventory contents or messages.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai.engine as engine
import ai.react as react
import ai.tools as tools
import core.operations as operations
import core.settings as config
import core.workflows as workflows
from core.agent_tasks import AgentTaskStore
from core.business_records import BusinessRecordService
from core.chat_service import ChatCoordinator
from core.conversations import ConversationManager
from core.file_security import validate_path
from core.inventory import InventoryService
from core.json_persistence import atomic_write_json
from core.operations import BusinessOperationsService
from core.settings import Settings, get_settings
from core.web_api.events import EventHub


def forbidden(*args, **kwargs):
    raise AssertionError("This direct action must not load a model or encoder")


def main():
    original = get_settings()
    database = validate_path(original.base_dir / "inventory.db")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            "SELECT nome,categoria,quantidade,estoque_min,estoque_max FROM inventory_items"
        ).fetchall()
    root = validate_path(original.data_dir / "latency_benchmarks", allow_create=True)
    root.mkdir(parents=True, exist_ok=True)
    report = {
        "scope": "real tools, read-only inventory snapshot, isolated persistence; no live WhatsApp sends",
        "inventory_item_count": len(rows),
        "cases": {},
    }
    with tempfile.TemporaryDirectory(dir=root) as directory:
        local = Path(directory)
        settings = Settings(
            base_dir=local, data_dir=local / "data", resources_dir=original.resources_dir
        )
        settings.features.memory = False
        settings.decision.enabled = False
        inventory = InventoryService(settings=settings, data_file=local / "inventory.json")
        for row in rows:
            inventory.adicionar_item(*row)
        records = BusinessRecordService(settings=settings, data_file=local / "records.json")
        ops = BusinessOperationsService(
            settings=settings, inventory_service=inventory, record_service=records
        )
        workflow = workflows.BusinessWorkflowService(
            settings=settings, record_service=records, operations_service=ops
        )
        coordinator = ChatCoordinator(
            settings=settings,
            event_hub=EventHub(),
            conversation_manager=ConversationManager(local / "conversations"),
            ensure_model_ready=forbidden,
        )
        try:
            with (
                patch.object(engine, "get_settings", return_value=settings),
                patch.object(react, "get_settings", return_value=settings),
                patch.object(tools, "get_settings", return_value=settings),
                patch.object(config, "get_settings", return_value=settings),
                patch.object(workflows, "get_workflow_service", return_value=workflow),
                patch.object(operations, "get_operations_service", return_value=ops),
                patch.object(react, "get_multi_model_manager", side_effect=forbidden),
                patch.object(react.tool_retrieval, "score_tools", side_effect=forbidden),
            ):
                for case, question in (
                    ("inventory_cold", "TAREFA: Gere uma relatório do meu estoque"),
                    ("inventory_warm", "TAREFA: Gere uma relatório do meu estoque"),
                    (
                        "news_current_week",
                        "TAREFA: liste as principais noticias de IA desta semana",
                    ),
                    (
                        "news_previous_week",
                        "TAREFA: liste as noticias sobre IA mais relevantes da semana passada",
                    ),
                ):
                    started = time.monotonic()
                    job = coordinator.submit(message=question, source="whatsapp")
                    while job["status"] not in {"completed", "failed", "cancelled"}:
                        if time.monotonic() - started > 60:
                            coordinator.cancel(job["id"])
                            raise TimeoutError("Direct action benchmark exceeded 60 seconds")
                        time.sleep(0.01)
                        job = coordinator.get_job(job["id"])
                    outputs = [coordinator.outputs.get(a["id"]) for a in job["attachments"]]
                    tasks = AgentTaskStore(settings.data_dir / "agent_tasks.db").list(
                        job["conversation_id"]
                    )
                    report["cases"][case] = {
                        "status": job["status"],
                        "task_status": tasks[0]["status"] if tasks else None,
                        "timings": job["timings"],
                        "attachments": len(outputs),
                        "pdf_verified": bool(outputs)
                        and all(a.path.read_bytes().startswith(b"%PDF") for a in outputs),
                        "source_links": job["response"].count("[Fonte]("),
                        "response_characters": len(job["response"]),
                        "contains_raw_table": "|---" in job["response"],
                    }
                    print(case, report["cases"][case], flush=True)
        finally:
            coordinator.shutdown()
    output = validate_path(
        original.data_dir / "logs/research-delivery-after.json", allow_create=True
    )
    atomic_write_json(output, report)
    print(f"Report: {output}")


if __name__ == "__main__":
    main()
