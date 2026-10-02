#!/usr/bin/env python3
"""Smoke test for Jev/Kev local decision server (port 8009).

Validates:
- Health check
- noul decision
- score decision
- choice decision
- Model selection between 2+ models
- Tool guard
- RAG gate
- Fallback with server down

Records latency, provider, model, response, and fallback behavior.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE_URL = "http://127.0.0.1:8009"
MODEL = "kev-latest"
TIMEOUT_MS = 5000


@dataclass
class SmokeResult:
    name: str
    success: bool
    latency_ms: float
    provider: str
    model: str
    response: Any
    error: str = ""
    fallback: bool = False


def _post(endpoint: str, payload: dict) -> tuple[dict | None, float, str, bool]:
    """Make a POST request to the decision server."""
    url = f"{BASE_URL}{endpoint}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = max(0.001, TIMEOUT_MS / 1000.0)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        elapsed = (time.perf_counter() - start) * 1000
        return raw, elapsed, "local", False
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        elapsed = (time.perf_counter() - start) * 1000
        return None, elapsed, "fallback", True


def _get(endpoint: str) -> tuple[dict | None, float, str, bool]:
    """Make a GET request to the decision server."""
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url, method="GET")
    timeout = max(0.001, TIMEOUT_MS / 1000.0)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        elapsed = (time.perf_counter() - start) * 1000
        return raw, elapsed, "local", False
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        elapsed = (time.perf_counter() - start) * 1000
        return None, elapsed, "fallback", True


def run_health_check() -> SmokeResult:
    """Test GET /v1/models (health check)."""
    raw, elapsed, provider, fallback = _get("/v1/models")
    if fallback or raw is None:
        return SmokeResult(
            name="health_check",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Server unreachable",
            fallback=True,
        )
    models = raw.get("models", [])
    model_names = [m.get("name") for m in models if isinstance(m, dict)]
    return SmokeResult(
        name="health_check",
        success=True,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"models": model_names},
    )


def run_noul_decision() -> SmokeResult:
    """Test noul (yes/no) decision."""
    payload = {
        "state": {"tipo_acao": "salvar_memoria", "argumentos": '{"texto": "teste"}'},
        "model": MODEL,
        "questions": {
            "altera_dados": {"type": "noul", "instructions": "Esta acao altera dados?"},
            "irreversivel": {"type": "noul", "instructions": "E irreversivel?"},
            "rede": {"type": "noul", "instructions": "Acede a rede?"},
            "destrutiva": {"type": "noul", "instructions": "E destrutiva?"},
        },
    }
    raw, elapsed, provider, fallback = _post("/v1/systemone", payload)
    if fallback or raw is None:
        return SmokeResult(
            name="noul_decision",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Request failed",
            fallback=True,
        )
    answers = raw.get("answers", {})
    nouls = {k: v.get("noul") for k, v in answers.items() if v.get("type") == "noul"}
    return SmokeResult(
        name="noul_decision",
        success=len(nouls) > 0,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"nouls": nouls},
    )


def run_score_decision() -> SmokeResult:
    """Test score (ordered scale) decision."""
    payload = {
        "state": {"consulta": "qual o saldo?", "trecho": "saldo atual e 100"},
        "model": MODEL,
        "questions": {
            "relevancia": {
                "type": "score",
                "criteria": ["irrelevante", "parcialmente relevante", "relevante"],
                "instructions": "O quanto este trecho ajuda?",
            }
        },
    }
    raw, elapsed, provider, fallback = _post("/v1/systemone", payload)
    if fallback or raw is None:
        return SmokeResult(
            name="score_decision",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Request failed",
            fallback=True,
        )
    answers = raw.get("answers", {})
    scores = {k: v.get("score") for k, v in answers.items() if v.get("type") == "score"}
    return SmokeResult(
        name="score_decision",
        success=len(scores) > 0,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"scores": scores},
    )


def run_choice_decision() -> SmokeResult:
    """Test choice (pick one) decision."""
    payload = {
        "state": {"consulta": "qual modelo usar?"},
        "model": MODEL,
        "questions": {
            "modelo": {
                "type": "choice",
                "criteria": {"model-a": "opcao A", "model-b": "opcao B"},
                "instructions": "Qual modelo?",
            }
        },
    }
    raw, elapsed, provider, fallback = _post("/v1/systemone", payload)
    if fallback or raw is None:
        return SmokeResult(
            name="choice_decision",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Request failed",
            fallback=True,
        )
    answers = raw.get("answers", {})
    choices = {k: v.get("choice") for k, v in answers.items() if v.get("type") == "choice"}
    return SmokeResult(
        name="choice_decision",
        success=len(choices) > 0,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"choices": choices},
    )


def run_model_routing() -> SmokeResult:
    """Test model routing between at least 2 models."""
    # We need at least 2 models installed to test this
    # First check what models are available
    raw, elapsed, provider, fallback = _get("/v1/models")
    if fallback or raw is None:
        return SmokeResult(
            name="model_routing",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Cannot check models",
            fallback=True,
        )
    models = raw.get("models", [])
    if len(models) < 2:
        return SmokeResult(
            name="model_routing",
            success=False,
            latency_ms=elapsed,
            provider=provider,
            model=MODEL,
            response={"models_available": len(models)},
            error=f"Need at least 2 models, only {len(models)} available",
        )

    # Test model routing decision
    payload = {
        "state": {
            "consulta": "analise profunda do codigo",
            "documento": "nao",
            "imagem": "nao",
        },
        "model": MODEL,
        "questions": {
            f"modelo_{m.get('name', f'model{i}')}": {
                "type": "score",
                "criteria": ["inadequado", "adequado", "ideal"],
                "instructions": f"Avalie o modelo '{m.get('name', f'model{i}')}' para a consulta.",
            }
            for i, m in enumerate(models[:3])  # Cap at 3 for speed
        },
    }
    raw, elapsed, provider, fallback = _post("/v1/systemone", payload)
    if fallback or raw is None:
        return SmokeResult(
            name="model_routing",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Request failed",
            fallback=True,
        )
    answers = raw.get("answers", {})
    scores = {k: v.get("score") for k, v in answers.items() if v.get("type") == "score"}
    return SmokeResult(
        name="model_routing",
        success=len(scores) >= 2,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"model_scores": scores},
    )


def run_tool_guard() -> SmokeResult:
    """Test tool guard decision."""
    payload = {
        "state": {"tipo_acao": "saida_estoque", "argumentos": '{"item_id": "1", "quantidade": 5}'},
        "model": MODEL,
        "questions": {
            "altera_dados": {"type": "noul", "instructions": "Altera dados?"},
            "irreversivel": {"type": "noul", "instructions": "E irreversivel?"},
            "rede": {"type": "noul", "instructions": "Acede a rede?"},
            "destrutiva": {"type": "noul", "instructions": "E destrutiva?"},
        },
    }
    raw, elapsed, provider, fallback = _post("/v1/systemone", payload)
    if fallback or raw is None:
        return SmokeResult(
            name="tool_guard",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Request failed",
            fallback=True,
        )
    answers = raw.get("answers", {})
    nouls = {k: v.get("noul") for k, v in answers.items() if v.get("type") == "noul"}
    max_noul = max(nouls.values()) if nouls else 0
    return SmokeResult(
        name="tool_guard",
        success=len(nouls) > 0,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"max_noul": max_noul, "details": nouls},
    )


def run_rag_gate() -> SmokeResult:
    """Test RAG gate decision."""
    payload = {
        "state": {"consulta": "qual o saldo?", "trecho": "saldo atual e 100"},
        "model": MODEL,
        "questions": {
            "relevancia": {
                "type": "score",
                "criteria": ["irrelevante", "parcialmente relevante", "relevante"],
                "instructions": "O quanto este trecho ajuda?",
            }
        },
    }
    raw, elapsed, provider, fallback = _post("/v1/systemone", payload)
    if fallback or raw is None:
        return SmokeResult(
            name="rag_gate",
            success=False,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response=None,
            error="Request failed",
            fallback=True,
        )
    answers = raw.get("answers", {})
    scores = {k: v.get("score") for k, v in answers.items() if v.get("type") == "score"}
    return SmokeResult(
        name="rag_gate",
        success=len(scores) > 0,
        latency_ms=elapsed,
        provider=provider,
        model=MODEL,
        response={"scores": scores},
    )


def run_fallback_test() -> SmokeResult:
    """Test fallback behavior with wrong port (simulate server down)."""
    # Use a port that should not have a server
    test_url = "http://127.0.0.1:9999/v1/models"
    req = urllib.request.Request(test_url, method="GET")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=1.0):
            elapsed = (time.perf_counter() - start) * 1000
            return SmokeResult(
                name="fallback_test",
                success=False,
                latency_ms=elapsed,
                provider="unexpected_success",
                model="",
                response=None,
                error="Expected server down but got response",
            )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        elapsed = (time.perf_counter() - start) * 1000
        return SmokeResult(
            name="fallback_test",
            success=True,
            latency_ms=elapsed,
            provider="fallback",
            model="",
            response={"expected": "server down"},
            fallback=True,
        )


def main():
    print("=" * 70)
    print("Jev/Kev Smoke Test - Local Decision Server (port 8009)")
    print("=" * 70)
    print()

    tests = [
        ("Health Check", run_health_check),
        ("Noul Decision", run_noul_decision),
        ("Score Decision", run_score_decision),
        ("Choice Decision", run_choice_decision),
        ("Model Routing", run_model_routing),
        ("Tool Guard", run_tool_guard),
        ("RAG Gate", run_rag_gate),
        ("Fallback (Server Down)", run_fallback_test),
    ]

    results: list[SmokeResult] = []
    for name, test_fn in tests:
        print(f"Running: {name}...")
        try:
            result = test_fn()
            results.append(result)
            status = "PASS" if result.success else "FAIL"
            fallback_note = " [FALLBACK]" if result.fallback else ""
            print(
                f"  {status}{fallback_note} - {result.latency_ms:.1f}ms - provider={result.provider}"
            )
            if result.error:
                print(f"  Error: {result.error}")
        except Exception as e:
            result = SmokeResult(
                name=name.lower().replace(" ", "_"),
                success=False,
                latency_ms=0,
                provider="error",
                model="",
                response=None,
                error=f"Exception: {e}",
            )
            results.append(result)
            print(f"  ERROR - {e}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r.success)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print()
    for r in results:
        status = "PASS" if r.success else "FAIL"
        fb = " (fallback)" if r.fallback else ""
        print(f"  [{status}] {r.name}: {r.latency_ms:.1f}ms, provider={r.provider}{fb}")

    # Save detailed results
    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "model": MODEL,
        "results": [
            {
                "name": r.name,
                "success": r.success,
                "latency_ms": r.latency_ms,
                "provider": r.provider,
                "model": r.model,
                "response": r.response,
                "error": r.error,
                "fallback": r.fallback,
            }
            for r in results
        ],
    }
    with open("jev_smoke_test_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("\nDetailed results saved to jev_smoke_test_results.json")

    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
