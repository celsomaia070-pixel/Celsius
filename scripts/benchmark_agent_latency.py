r"""Local, isolated latency evaluation. Never opens user documents or invokes tools.

Run: .venv\Scripts\python scripts\benchmark_agent_latency.py [--model]
Reports contain case IDs, timings and counts, never prompt/response contents.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.chat_service import ChatCoordinator
from core.conversations import ConversationManager
from core.file_security import validate_path
from core.json_persistence import atomic_write_json
from core.operation_control import OperationCancelled, bind_control
from core.settings import Settings, get_settings
from core.turn_metrics import TurnMetrics, bind_metrics
from core.web_api.events import EventHub


def run_fast(original):
    root = validate_path(original.base_dir / "data" / "latency_benchmarks", allow_create=True)
    root.mkdir(parents=True, exist_ok=True)
    cases = {
        "identity": "quem é voce?",
        "capabilities": "olá me diga as suas capacidades",
        "legacy_identity": "TAREFA: quem é voce?",
        "legacy_capabilities": "TAREFA: olá me diga as suas capacidades",
    }
    results = {}
    with tempfile.TemporaryDirectory(dir=root) as directory:
        local = Path(directory)
        settings = Settings(
            base_dir=local,
            data_dir=local / "data",
            logs_dir=local / "logs",
            resources_dir=original.resources_dir,
        )
        coordinator = ChatCoordinator(
            settings=settings,
            event_hub=EventHub(),
            conversation_manager=ConversationManager(local / "conversations"),
        )
        try:
            for case, text in cases.items():
                durations = []
                for _ in range(25):
                    start = time.perf_counter()
                    job = coordinator.submit(
                        message=text,
                        work_mode=True,
                        agent_mode="executor",
                        work_agents=["executor", "documentos"],
                    )
                    durations.append((time.perf_counter() - start) * 1000)
                    assert job["status"] == "completed", job["status"]
                    assert job["timings"]["model_state"] == "not_used"
                    assert coordinator._jobs[job["id"]].future is None
                results[case] = {
                    "samples": len(durations),
                    "median_ms": statistics.median(durations),
                    "max_ms": max(durations),
                    "p95_ms": sorted(durations)[23],
                    "last_timings": job["timings"],
                    "model_calls": 0,
                }
        finally:
            coordinator.shutdown()
    return results


def run_pipeline(settings, manager):
    from unittest.mock import patch

    import ai.engine as engine
    import ai.react as react

    class FixedModel:
        def route_and_invoke(self, *args, **kwargs):
            return settings.llm_model, manager

        def get_current_complexity(self):
            return "simple"

        def get_last_decision(self):
            return None

    root = validate_path(settings.base_dir / "data/latency_benchmarks", allow_create=True)
    with tempfile.TemporaryDirectory(dir=root) as directory:
        local = Path(directory)
        isolated = Settings(
            base_dir=local,
            data_dir=local / "data",
            logs_dir=local / "logs",
            resources_dir=settings.resources_dir,
        )
        isolated.model = settings.model.model_copy(deep=True)
        coordinator = ChatCoordinator(
            settings=isolated,
            event_hub=EventHub(),
            conversation_manager=ConversationManager(local / "conversations"),
        )
        try:
            with (
                patch.object(engine, "get_settings", return_value=isolated),
                patch.object(react, "get_settings", return_value=isolated),
                patch.object(react, "get_multi_model_manager", return_value=FixedModel()),
            ):
                job = coordinator.submit(
                    message="Quanto é 2 + 2? Responda somente com o resultado.", work_mode=True
                )
                deadline = time.monotonic() + 130
                while job["status"] not in {"completed", "failed", "cancelled"}:
                    if time.monotonic() > deadline:
                        coordinator.cancel(job["id"])
                        raise TimeoutError("Pipeline evaluation exceeded its deadline")
                    time.sleep(0.02)
                    job = coordinator.get_job(job["id"])
                return {
                    "scope": "real responder + ReAct + persistence; model routing held fixed; no tools",
                    "status": job["status"],
                    "intent": job["intent"],
                    "timings": job["timings"],
                    "answer_is_four": job["response"].strip().strip(".* ") == "4",
                    "characters": len(job["response"]),
                    "agents": job["work_agents"],
                }
        finally:
            coordinator.shutdown()


def run_model(settings, *, pipeline=False, verbose=False):
    from core.llama_cpp import get_llama_manager
    from core.model_router import model_start_kwargs

    manager = get_llama_manager()
    params = model_start_kwargs(settings.llm_model)
    params.update(
        n_batch=settings.model.n_batch,
        n_threads=settings.model.n_threads,
        use_mmap=settings.model.use_mmap,
        use_mlock=settings.model.use_mlock,
    )
    report = {
        "model_id": settings.llm_model,
        "parameters": params,
        "scope": "native model, no RAG/tools",
    }
    start = time.perf_counter()
    print("Loading the configured local model...", flush=True)
    assert manager.start(model_id=settings.llm_model, verbose=verbose, **params), (
        "Local model did not start"
    )
    report["cold_load_ms"] = (time.perf_counter() - start) * 1000
    report["runtime"] = manager.runtime_info()
    print(f"Cold load: {report['cold_load_ms']:.1f} ms", flush=True)
    try:
        for case, question in (
            ("cold_generation", "Explique em duas frases por que o céu é azul."),
            ("warm_generation", "Explique em duas frases por que a Lua tem fases."),
        ):
            metrics = TurnMetrics(model_state="cold" if case.startswith("cold") else "warm")
            chunks = []
            finish_reason = None
            with bind_metrics(metrics), bind_control(None, time.monotonic() + 180):
                stream = manager.create_chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": "Responda em português, diretamente e brevemente. /no_think",
                        },
                        {"role": "user", "content": question},
                    ],
                    temperature=0.1,
                    max_tokens=160,
                    stream=True,
                )
                try:
                    for chunk in stream:
                        finish_reason = chunk["choices"][0].get("finish_reason") or finish_reason
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            metrics.first_token()
                            chunks.append(content)
                finally:
                    stream.close()
            metrics.finish()
            text = "".join(chunks)
            report[case] = {
                "timings": metrics.public_dict(),
                "characters": len(text),
                "content_chunks": len(chunks),
                "nonempty": bool(text.strip()),
                "contains_reasoning_marker": "<think>" in text,
                "finish_reason": finish_reason,
                "truncated": finish_reason == "length",
            }
            print(case, report[case], flush=True)

        cancel = threading.Event()
        interrupted = False
        start = time.perf_counter()
        stream = manager.create_chat_completion(
            messages=[{"role": "user", "content": "Conte de um a cem."}],
            stream=True,
            max_tokens=160,
            should_cancel=cancel.is_set,
        )
        try:
            for chunk in stream:
                if chunk["choices"][0]["delta"].get("content"):
                    cancel.set()
                    start = time.perf_counter()
        except OperationCancelled:
            interrupted = True
        finally:
            stream.close()
        report["cancel"] = {
            "observed": interrupted,
            "after_first_chunk_ms": (time.perf_counter() - start) * 1000,
            "inference_lock_released": not manager.is_inference_busy(),
        }
        if pipeline:
            print("Evaluating the real common responder with fixed model routing...", flush=True)
            report["common_pipeline"] = run_pipeline(settings, manager)
            print(report["common_pipeline"], flush=True)
    finally:
        manager.stop()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", action="store_true", help="Load the configured GGUF for real local inference"
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Also evaluate the common responder on the same model",
    )
    parser.add_argument(
        "--verbose-model", action="store_true", help="Record native offload diagnostics"
    )
    parser.add_argument("--output", default="data/logs/agent-latency-after.json")
    args = parser.parse_args()
    settings = get_settings()
    report = {"fast_coordinator_real_persistence": run_fast(settings)}
    path = validate_path(settings.base_dir / args.output, allow_create=True)
    atomic_write_json(path, report)
    print(report, flush=True)
    if args.model:
        try:
            report["real_model"] = run_model(
                settings, pipeline=args.pipeline, verbose=args.verbose_model
            )
        except Exception as exc:
            report["real_model_failure"] = type(exc).__name__
            raise
        finally:
            atomic_write_json(path, report)
    print(f"Report: {path}", flush=True)


if __name__ == "__main__":
    main()
