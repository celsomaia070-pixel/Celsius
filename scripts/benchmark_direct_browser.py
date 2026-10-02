"""Measure routing and approvals with real persistence and a simulated OS browser launch.

Never sends WhatsApp messages, opens the browser or calls a model/encoder.
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai.engine as engine
import ai.react as react
import ai.tools as tools
from core.agent_tasks import AgentTaskStore
from core.chat_service import ChatCoordinator
from core.conversations import ConversationManager
from core.file_security import validate_path
from core.json_persistence import atomic_write_json
from core.settings import Settings, get_settings
from core.web_api.events import EventHub


def forbidden(*args, **kwargs):
    raise AssertionError("A direct browser request must not load a model or encoder")


def main():
    original = get_settings()
    root = validate_path(original.data_dir / "latency_benchmarks", allow_create=True)
    root.mkdir(parents=True, exist_ok=True)
    report = {"scope": "real coordinator and persistence; OS browser launch simulated", "cases": {}}
    durations = {"prepare_approval": [], "authorized_open": []}
    with tempfile.TemporaryDirectory(dir=root) as directory:
        local = Path(directory)
        settings = Settings(base_dir=local, data_dir=local / "data")
        coordinator = ChatCoordinator(
            settings=settings,
            event_hub=EventHub(),
            conversation_manager=ConversationManager(local / "conversations"),
            ensure_model_ready=forbidden,
        )
        store = AgentTaskStore(settings.data_dir / "agent_tasks.db")

        def send(text, conversation_id=""):
            job = coordinator.submit(
                message=text, conversation_id=conversation_id, source="whatsapp"
            )
            deadline = time.monotonic() + 5
            while job["status"] not in {"completed", "failed", "cancelled"}:
                assert time.monotonic() < deadline
                time.sleep(0.002)
                job = coordinator.get_job(job["id"])
            assert job["status"] == "completed", job.get("error")
            assert job["timings"]["model_state"] == "not_used"
            return job

        try:
            with (
                patch.object(engine, "get_settings", return_value=settings),
                patch.object(react, "get_settings", return_value=settings),
                patch.object(tools, "get_settings", return_value=settings),
                patch.object(react.tool_retrieval, "score_tools", side_effect=forbidden),
                patch.object(react, "get_multi_model_manager", side_effect=forbidden),
                patch("webbrowser.open", return_value=True) as browser,
            ):
                for _ in range(25):
                    initial = send("TAREFA: Abra o YouTube em Tim Maia")
                    durations["prepare_approval"].append(initial["timings"]["total_ms"])
                    task = store.list(initial["conversation_id"])[0]
                    assert task["status"] == "waiting_confirmation"
                    approved = send(
                        "AUTORIZAR " + task["steps"][0]["approval_code"], initial["conversation_id"]
                    )
                    durations["authorized_open"].append(approved["timings"]["total_ms"])
                    assert (
                        store.get(task["id"], initial["conversation_id"])["status"] == "completed"
                    )
                assert browser.call_count == 25
        finally:
            coordinator.shutdown()
    for case, samples in durations.items():
        report["cases"][case] = {
            "samples": len(samples),
            "median_ms": statistics.median(samples),
            "p95_ms": sorted(samples)[23],
            "max_ms": max(samples),
            "model_calls": 0,
            "encoder_calls": 0,
        }
    path = validate_path(original.data_dir / "logs/youtube-routing-after.json", allow_create=True)
    atomic_write_json(path, report)
    print(report)


if __name__ == "__main__":
    main()
