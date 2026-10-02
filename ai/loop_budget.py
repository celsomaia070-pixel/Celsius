"""Execution budget for the ReAct loop: how many iterations, and when to stop.

``ai.react.loop_react`` used to choose between exactly two numbers — 5 for a
normal chat turn, 200 when a ``TaskSession`` was present. A mode's own
``max_iterations`` (12/36/40/60/80) was never consulted on the chat path at all,
so a legitimate multi-step request had five turns to find a document, read it,
transform it and save the result.

Five is not a safety limit, it is a leftover. The real risk is not "too many
iterations" but "the same iteration again", and that is a different mechanism:
see :class:`LoopDetector`.

Three independent brakes, each with its own job:

* **Complexity budget** — a greeting does not get a document workflow's budget.
* **Hard cap** — a misconfigured mode cannot run unbounded.
* **Loop detection** — repeating the same call stops being an option.

Every knob is in ``core.settings.AgentModeSettings``; nothing here hardcodes a
limit. The budget is a *policy decision*, kept out of ``ai.react`` so it can be
tested without a model.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ai.tool_result import ToolResult
from ai.tool_retrieval import _normalize
from core.settings import get_settings

logger = logging.getLogger(__name__)

# ── Complexity classes ──────────────────────────────────────────

CONVERSA = "conversa"
FERRAMENTA_SIMPLES = "ferramenta_simples"
MULTI_STEP = "multi_step"
TAREFA = "task"

#: Sequencing markers. "Leia, resuma e salve" is one request with three
#: required actions; a single keyword match cannot see that, but a conjunction
#: plus a sequence marker reliably can.
_SEQUENCE_PATTERN = re.compile(
    r"(?<!\w)(?:"
    r"e depois|depois disso|em seguida|logo apos|"
    r"por fim|no fim|finalmente|"
    r"depois|"
    r"e salve|e grave|e gere|e faca|e leia|e resuma|e processe|e copie|e mova|e envie|"
    r"em outro|no outro|"
    r"passo a passo|"
    r"primeiro.*depois"
    r")(?!\w)"
)

#: Verbs that each imply a distinct action on local data. Two or more different
#: ones in one sentence is a multi-step request even without a sequence marker.
_ACTION_GROUPS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "leia",
            "ler",
            "le",
            "abra",
            "abrir",
            "consulte",
            "consultar",
            "veja",
            "ver",
            "mostre",
            "mostrar",
            "liste",
            "listar",
            "busque",
            "buscar",
            "procure",
            "procurar",
            "recupere",
            "recuperar",
        }
    ),
    frozenset(
        {
            "resuma",
            "resumir",
            "resumo",
            "transforme",
            "transformar",
            "organize",
            "organizar",
            "extraia",
            "extrair",
            "processe",
            "processar",
            "converta",
            "converter",
            "reformate",
            "reformatar",
            "limpe",
            "limpar",
            "analise",
            "analisar",
        }
    ),
    frozenset(
        {
            "salve",
            "salvar",
            "grave",
            "gravar",
            "escreva",
            "escrever",
            "crie",
            "criar",
            "gere",
            "gerar",
            "exporte",
            "exportar",
            "guarde",
            "guardar",
            "adicione",
            "cadastre",
            "registre",
            "anexe",
            "envie",
            "imprima",
        }
    ),
)


@dataclass(frozen=True)
class Complexity:
    """How much room this request deserves, and why."""

    kind: str
    signals: tuple[str, ...] = field(default=())


def classify_complexity(
    pergunta: str,
    *,
    ferramentas: list[str] | None = None,
    task_session: Any = None,
) -> Complexity:
    """Decide the complexity class of one turn.

    Deliberately mechanical. Every rule here has to be justifiable in one
    sentence, because a wrong classification either starves a real task or pays
    for turns that will never be used.

    Precedence, highest first: a task session, a sequencing or multi-action
    request, a request that carries tools, and finally a plain conversation.
    """
    if task_session:
        return Complexity(TAREFA, ("task_session",))

    texto = _normalize(pergunta)
    if not texto.strip():
        return Complexity(CONVERSA, ("vazio",))

    # Sequencing markers are the strongest single signal: "leia, resuma e
    # salve" cannot be answered in one action however the keywords fall.
    sequencia = _SEQUENCE_PATTERN.search(texto)
    if sequencia:
        return Complexity(MULTI_STEP, (f"sequencia:{sequencia.group(0)}",))

    grupos_ativos = [sorted(g & set(texto.split())) for g in _ACTION_GROUPS]
    acoes_distintas = [g for g in grupos_ativos if g]
    if len(acoes_distintas) >= 2:
        return Complexity(MULTI_STEP, tuple(f"acoes:{','.join(g)}" for g in acoes_distintas))

    if ferramentas:
        return Complexity(FERRAMENTA_SIMPLES, (f"ferramentas:{len(ferramentas)}",))

    return Complexity(CONVERSA, ("sem_ferramenta",))


# ── Budget ──────────────────────────────────────────────────────


def resolve_budget(
    pergunta: str,
    *,
    mode: Any = None,
    ferramentas: list[str] | None = None,
    task_session: Any = None,
    settings_agent: Any = None,
) -> tuple[int, Complexity]:
    """Iterations this turn may spend, and the class it was derived from.

    For a task session the mode's own ``max_iterations`` is authoritative — it
    is the one value a mode declares about itself, and ``TaskSession`` already
    accounts iterations across slices. The hard cap still applies, so a mode
    declaring 5000 cannot buy 5000 turns.

    For a chat turn the class picks the tier. The old constant was 5 for every
    request; the tiers keep a greeting cheap while giving a multi-step request
    room to finish.
    """
    settings = settings_agent if settings_agent is not None else get_settings().agent
    complexity = classify_complexity(pergunta, ferramentas=ferramentas, task_session=task_session)
    cap = max(1, int(settings.loop_hard_cap))

    if complexity.kind == TAREFA:
        declarado = int(getattr(mode, "max_iterations", 0) or 0)
        base = declarado or int(settings.loop_budget_task)
    elif complexity.kind == MULTI_STEP:
        base = int(settings.loop_budget_multi_step)
    elif complexity.kind == FERRAMENTA_SIMPLES:
        base = int(settings.loop_budget_ferramenta_simples)
    else:
        base = int(settings.loop_budget_conversa)

    logger.debug(
        "orcamento de loop: classe=%s base=%s cap=%s sinais=%s",
        complexity.kind,
        base,
        cap,
        ",".join(complexity.signals),
    )
    return max(1, min(base, cap)), complexity


# ── Loop detection ──────────────────────────────────────────────


@dataclass(frozen=True)
class Repetition:
    """A call that adds nothing to the previous one.

    ``same_arguments`` and ``same_error`` are reported separately because they
    have different causes: identical arguments usually mean the model is stuck,
    while the same error from *different* arguments usually means the tool or
    the environment is the problem, and retrying harder will not help.
    """

    tool: str
    consecutive: int
    same_arguments: bool
    same_error: bool
    signature: str

    @property
    def actionable(self) -> bool:
        return self.same_arguments or self.same_error


class LoopDetector:
    """Tracks consecutive equivalent tool calls within one turn.

    Only *consecutive* repeats count. Calling ``listar_documentos_rag``,
    ``ler_arquivo`` and then ``listar_documentos_rag`` again is a sensible plan,
    not a loop; a reset on every different call would hide exactly the
    oscillation this is meant to catch.

    The first repeat is a warning and the threshold is a stop, so the model gets
    one chance to notice and change strategy before the loop is broken for it.
    """

    def __init__(self, *, threshold: int | None = None, settings_agent: Any = None) -> None:
        settings = settings_agent if settings_agent is not None else get_settings().agent
        self.threshold = max(
            1, int(settings.loop_repeat_threshold if threshold is None else threshold)
        )
        self._signature: str | None = None
        self._error: str | None = None
        self._error_repeats = 0
        self.consecutive = 0
        self.history: list[str] = []

    @staticmethod
    def _call_signature(nome: str, args: Any) -> str:
        try:
            return f"{nome}:{json.dumps(args, sort_keys=True, default=str)}"
        except (TypeError, ValueError):
            return f"{nome}:{args!r}"

    def register(
        self, nome: str, args: Any, resultado: Any = None, *, falhou: bool = False
    ) -> Repetition | None:
        """Record one call. Returns a :class:`Repetition` when it repeats.

        ``None`` means the call advanced the trajectory.
        """
        signature = self._call_signature(nome, args)
        erro = _error_fingerprint(resultado) if falhou else None

        if signature == self._signature:
            self.consecutive += 1
        else:
            self.consecutive = 1
            self._signature = signature

        if erro is not None and erro == self._error:
            self._error_repeats += 1
        elif erro is not None:
            self._error = erro
            self._error_repeats = 1
        else:
            self._error = None
            self._error_repeats = 0

        self.history.append(signature)
        # Two independent ways to be stuck: the same call, or the same failure
        # whatever the arguments were.  The second one matters because a model
        # retrying a rejected write usually varies the arguments slightly, and
        # comparing only the signature would let that run forever.
        repeticao_argumentos = self.consecutive >= 2
        repeticao_erro = erro is not None and self._error_repeats >= 2
        if not repeticao_argumentos and not repeticao_erro:
            return None

        return Repetition(
            tool=nome,
            consecutive=max(self.consecutive, self._error_repeats),
            same_arguments=repeticao_argumentos,
            same_error=repeticao_erro,
            signature=signature,
        )

    @property
    def exhausted(self) -> bool:
        """Whether the loop must be broken for the model."""
        return self.consecutive >= self.threshold or self._error_repeats >= self.threshold

    def nudge(self, repetition: Repetition) -> str:
        """The observation appended to the conversation to force a change.

        Phrased as a constraint rather than a complaint, because the model
        responds to "do X instead" far better than to "you are looping".
        """
        if repetition.same_error:
            return (
                f"A ferramenta '{repetition.tool}' ja falhou {repetition.consecutive} vezes "
                "com o mesmo resultado. Repetir a mesma chamada nao vai mudar o "
                "resultado. Mude de estrategia: use outra ferramenta, ajuste os "
                "argumentos com base no que a ferramenta respondeu, ou explique ao "
                "usuario o que impediu a conclusao."
            )
        return (
            f"A ferramenta '{repetition.tool}' ja foi chamada {repetition.consecutive} "
            "vezes seguidas com os mesmos argumentos, entao ela nao esta acrescentando "
            "nada. Use o que ja foi obtido para responder, chame outra ferramenta, ou "
            "mude os argumentos. Nao repita esta chamada."
        )


def _error_fingerprint(resultado: Any) -> str | None:
    """A stable key for "the same failure", ignoring the varying noise.

    Tool errors carry paths, ids and counters that change between identical
    failures; comparing the whole string would report a fresh problem every
    time and defeat the detector.

    Prefers ``ToolResult.error.code`` when available; falls back to a
    normalised string prefix for legacy results.
    """
    if resultado is None:
        return None

    # Structured error: use the code + message prefix for stable grouping
    if isinstance(resultado, ToolResult) and not resultado.ok and resultado.error:
        return f"{resultado.error.code.value}:{resultado.error.message[:80]}"

    texto = _normalize(resultado)
    if not texto:
        return None
    collapsed = " ".join(texto.split())
    # Keep only the leading clause: it carries the error kind and the field.
    return collapsed[:120]
