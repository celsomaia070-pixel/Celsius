"""Conditional reflection/verification for the ReAct loop.

Only triggers when specific conditions suggest the answer may be incomplete
or inconsistent. Avoids an extra LLM call for every response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReflectionResult:
    """Outcome of a reflection step."""

    needs_action: bool
    reason: str
    suggested_tool: str | None = None
    suggested_args: dict | None = None


# Triggers that warrant reflection (kept as simple predicates for testability)


def _tools_were_expected_but_none_used(
    pergunta: str,
    ferramentas_ofertadas: list[str],
    passos: list[Any],
) -> bool:
    """User asked something operational but model used zero tools."""
    if not ferramentas_ofertadas:
        return False
    if any(p.tipo == "acao" for p in passos):
        return False
    # Heuristic: question contains operational verbs but no tool was called
    texto = (pergunta or "").lower()
    operational_verbs = (
        "liste",
        "busque",
        "encontre",
        "leia",
        "salve",
        "crie",
        "gere",
        "consulte",
        "verifique",
        "processe",
        "transforme",
        "exporte",
        "quantos",
        "qual",
        "quais",
        "onde",
        "quando",
    )
    return any(v in texto for v in operational_verbs)


def _tool_failed_and_no_retry(
    passos: list[Any],
) -> bool:
    """A tool failed and the model answered without retrying."""
    for p in passos:
        if p.tipo == "observacao" and p.resultado:
            res = str(p.resultado).lower()
            if res.startswith(("erro", "serviço", "falha")):
                # Check if any subsequent action tried to fix it
                later_actions = [
                    p2 for p2 in passos if p2.tipo == "acao" and passos.index(p2) > passos.index(p)
                ]
                if not later_actions:
                    return True
    return False


def _answer_contradicts_tool_result(
    resposta: str,
    passos: list[Any],
) -> bool:
    """Model's final answer contradicts a tool result (very rough heuristic)."""
    # This is a placeholder — real implementation would need semantic comparison
    # For now, we only flag if the answer says "não encontrei" but a tool returned data
    resposta_lower = (resposta or "").lower()
    for p in passos:
        if p.tipo == "observacao" and p.resultado:
            res = str(p.resultado)
            if (
                res
                and not res.lower().startswith(("erro", "serviço", "falha"))
                and ("não encontrei" in resposta_lower or "não há" in resposta_lower)
            ):
                return True
    return False


def _ended_by_iteration_limit(
    max_iteracoes: int,
    iteracao_atual: int,
) -> bool:
    """Loop ended because it hit the iteration cap."""
    return iteracao_atual >= max_iteracoes - 1


def _task_incomplete(
    passos: list[Any],
    task_session: Any,
) -> bool:
    """Task session exists but has no final output."""
    if not task_session:
        return False
    if getattr(task_session, "output", None):
        return False
    # Check if there's a plan that wasn't fully executed
    plan = getattr(task_session, "task", {}).get("plan")
    if plan:
        return True
    return False


def should_reflect(
    pergunta: str,
    resposta: str,
    ferramentas_ofertadas: list[str],
    passos: list[Any],
    task_session: Any,
    max_iteracoes: int,
    iteracao_atual: int,
) -> bool:
    """Whether a reflection step is warranted.

    Conditions (any one triggers):
    1. Operational question but zero tools used
    2. Tool failed and no retry attempted
    3. Answer appears to contradict tool result
    4. Hit iteration limit
    5. Task session with incomplete plan
    """
    return (
        _tools_were_expected_but_none_used(pergunta, ferramentas_ofertadas, passos)
        or _tool_failed_and_no_retry(passos)
        or _answer_contradicts_tool_result(resposta, passos)
        or _ended_by_iteration_limit(max_iteracoes, iteracao_atual)
        or _task_incomplete(passos, task_session)
    )


def reflect(
    pergunta: str,
    resposta: str,
    ferramentas_ofertadas: list[str],
    passos: list[Any],
    task_session: Any,
    *,
    max_iteracoes: int,
    iteracao_atual: int,
    summarize_fn: Any | None = None,
) -> ReflectionResult:
    """Run a lightweight reflection using the model (or local fallback).

    In production this would call a small verification prompt. For now we
    implement the decision logic locally and return a structured result.
    The caller can decide to act on `needs_action` by continuing the loop.
    """
    reasons = []
    suggested_tool = None
    suggested_args = None

    if _tools_were_expected_but_none_used(pergunta, ferramentas_ofertadas, passos):
        reasons.append("Pergunta operacional sem uso de ferramentas")
        # Suggest the first relevant tool as a nudge
        if ferramentas_ofertadas:
            suggested_tool = ferramentas_ofertadas[0]

    if _tool_failed_and_no_retry(passos):
        reasons.append("Ferramenta falhou sem nova tentativa")

    if _answer_contradicts_tool_result(resposta, passos):
        reasons.append("Resposta contradiz resultado de ferramenta")

    if _ended_by_iteration_limit(max_iteracoes, iteracao_atual):
        reasons.append("Limite de iterações atingido")

    if _task_incomplete(passos, task_session):
        reasons.append("Tarefa com plano incompleto")

    if not reasons:
        return ReflectionResult(needs_action=False, reason="Nenhum gatilho")

    return ReflectionResult(
        needs_action=True,
        reason="; ".join(reasons),
        suggested_tool=suggested_tool,
        suggested_args=suggested_args,
    )
