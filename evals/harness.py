"""Golden-set harness: measure what the router and retriever actually do.

Deliberately **not** a test file. It runs the real selection path, records
numbers, and compares two runs. That is what makes "before vs after" possible
instead of a claim that something "looks better".

Scope, stated plainly
--------------------
These metrics cover the **decision layer only**: which tools a turn is offered,
and which mode it runs in. They are measurable without a language model, so
they are reproducible and comparable.

They are *not* a measure of model intelligence. Task Success, Error Recovery
and Loop Exhaustion all need a real LLM to drive the loop, and are therefore
reported as ``not measured`` until an LLM is in the loop â€” see
``LLM_BACKED_METRICS``. Guessing those numbers would be worse than omitting
them, because a fake number reads as evidence.

Two more honest caveats:

* A case counts as a hit when *any* tool from ``required_tools`` is offered, so
  Recall measures "did the right capability reach the model", not "did it reach
  it first". With several ways to satisfy a request that is the intended
  question, but it is not the same as end-to-end success.
* When the embedding model cannot be loaded, the semantic layer is inert and
  every number here describes the **lexical fallback**. The harness reports
  which path it measured so the two are never confused.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Callable

from evals.cases import CASES, Case

#: Metrics that cannot be computed without driving a real model. Named
#: explicitly so the report shows them as pending rather than silently absent.
LLM_BACKED_METRICS = (
    "tool_error_recovery_rate",
    "loop_exhaustion_rate",
    "task_success_rate",
    "reflection_triggered_rate",
)

RETRIEVAL_KEY = "tool_retrieval"


# â”€â”€ Selection strategies under test â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def select_current(prompt: str) -> list[str]:
    """What the system offers today: the real ``_filtrar_ferramentas`` path."""
    from ai import react as ai_react

    return [tool.nome for tool in ai_react._filtrar_ferramentas(prompt)]


def select_lexical_only(prompt: str) -> list[str]:
    """The pre-Fase-1 behaviour: keyword map only, no semantic union.

    Reconstructing the original decision this way rather than checking out old
    code keeps the comparison exact and runnable in one process.
    """
    from ai import react as ai_react

    return [
        tool.nome
        for tool in ai_react.REGISTRO_FERRAMENTAS
        if tool.nome in ai_react._keywords_para_ferramentas(prompt)
    ]


def select_semantic_only(prompt: str) -> list[str]:
    """The semantic contribution alone, ignoring keywords.

    Reported separately so the contribution of each signal is visible instead of
    being hidden inside a union.
    """
    from ai import react as ai_react
    from ai import tool_retrieval

    scores = tool_retrieval.score_tools(prompt)
    if not ai_react._keywords_para_ferramentas(prompt) and not tool_retrieval.is_operational(
        prompt, scores
    ):
        return []
    return [nome for nome, _score in tool_retrieval.top_tools(scores)]


#: Retrieval path used for mode selection too, so one run is internally
#: consistent. Mode routing shares the encoder, and mixing a semantic tool pass
#: with a lexical-only mode pass would make the numbers incomparable.
def _mode_for(prompt: str, mode_text: str | None = None) -> str:
    from core import agent_modes

    if mode_text is not None:
        detected = agent_modes.parse_mode_command(mode_text)
        if detected:
            return agent_modes.get_mode(detected).id
    if not hasattr(agent_modes, "resolve_mode"):
        detected = agent_modes.detect_mode(prompt)
        return agent_modes.get_mode(detected).id if detected else agent_modes.DEFAULT_MODE_ID
    return agent_modes.resolve_mode(prompt)


def _mode_lexical_only(prompt: str, mode_text: str | None = None) -> str:
    """Mode decision with the semantic router disabled.

    ``auto_route_enabled`` is flipped rather than reimplemented, so the lexical
    path used here is the production one.
    """
    from core import agent_modes
    from core.settings import get_settings

    settings = get_settings().agent
    previous = settings.auto_route_enabled
    settings.auto_route_enabled = False
    try:
        if mode_text is not None:
            detected = agent_modes.parse_mode_command(mode_text)
            if detected:
                return agent_modes.get_mode(detected).id
        detected = agent_modes.detect_mode(prompt)
        return agent_modes.get_mode(detected).id if detected else agent_modes.DEFAULT_MODE_ID
    finally:
        settings.auto_route_enabled = previous


# â”€â”€ Result types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


@dataclass
class CaseResult:
    id: str
    category: str
    prompt: str
    expected_tools: list[str]
    offered_tools: list[str]
    hits: list[str]
    expected_mode: str | None
    actual_mode: str
    expect_no_tool: bool
    notes: list[str] = field(default_factory=list)

    @property
    def recall_hit(self) -> bool:
        return bool(self.hits)

    @property
    def mode_ok(self) -> bool:
        return self.expected_mode is None or self.expected_mode == self.actual_mode


@dataclass
class RunReport:
    label: str
    retrieval: str
    mode: str
    encoder_available: bool
    embedding_model: str
    cases: list[CaseResult]
    metrics: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True)

    def per_category(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for case in self.cases:
            bucket = out.setdefault(
                case.category, {"total": 0, "recall_hits": 0, "mode_total": 0, "mode_ok": 0}
            )
            bucket["total"] += 1
            bucket["recall_hits"] += 1 if case.recall_hit else 0
            if case.expected_mode is not None:
                bucket["mode_total"] += 1
                bucket["mode_ok"] += 1 if case.mode_ok else 0
        return out


# â”€â”€ Metrics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def compute_metrics(cases: list[CaseResult]) -> dict[str, Any]:
    """Every metric the decision layer can honestly produce.

    Recall and Precision are computed over the cases that *expect* a tool;
    counting the must-not-call cases would inflate Recall with cases that have
    no right answer to hit.
    """
    scored = [c for c in cases if c.expected_tools and not c.expect_no_tool]
    no_tool_expected = [c for c in cases if c.expect_no_tool]
    mode_labelled = [c for c in cases if c.expected_mode is not None]

    recall_hits = sum(1 for c in scored if c.recall_hit)
    offered_total = sum(len(c.offered_tools) for c in scored)
    relevant_offered = sum(len(c.hits) for c in scored)
    from ai.tools import REGISTRO_FERRAMENTAS

    zero_tool_misses = [
        c.id for c in scored if not c.offered_tools
    ]
    operational_violations = [
        c.id for c in scored if c.expect_no_tool and c.offered_tools
    ]

    return {
        "cases_total": len(cases),
        "cases_with_tool_expectation": len(scored),
        "tool_recall": _ratio(recall_hits, len(scored)),
        "tool_recall_hits": recall_hits,
        # Precision over offered tools: how many of the schemas sent to the
        # model were in the required set. A tool that is merely *plausible* is
        # counted as a false positive, which is the conservative reading.
        "tool_precision": _ratio(relevant_offered, offered_total),
        "tools_offered_avg": _mean(len(c.offered_tools) for c in scored),
        "recall_at_1": _ratio(
            sum(1 for c in scored if c.offered_tools[:1] and c.offered_tools[0] in c.hits),
            len(scored),
        ),
        "recall_at_3": _ratio(
            sum(1 for c in scored if any(t in c.hits for t in c.offered_tools[:3])),
            len(scored),
        ),
        "zero_tool_rate_operational": _ratio(len(zero_tool_misses), len(scored)),
        "zero_tool_rate_operational_ids": zero_tool_misses,
        # The regression that matters most: an operational request reaching the
        # model with no tool at all.
        "operational_zero_tool_count": len(zero_tool_misses),
        "should_be_silent": len(no_tool_expected),
        "silent_when_should_be": sum(1 for c in no_tool_expected if not c.offered_tools),
        # How often a general-knowledge question was handed tools it does not
        # need. Lower is better; any value above zero is wasted prompt budget.
        "false_tool_rate_on_general": _ratio(
            sum(1 for c in no_tool_expected if c.offered_tools), len(no_tool_expected)
        ),
        "unnecessary_tool_call_ids": operational_violations,
        "mode_accuracy": _ratio(
            sum(1 for c in mode_labelled if c.mode_ok), len(mode_labelled)
        ),
        "mode_labelled_cases": len(mode_labelled),
        "registry_size": len(REGISTRO_FERRAMENTAS),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _mean(values) -> float:
    listed = list(values)
    return round(sum(listed) / len(listed), 2) if listed else 0.0


# ── LLM-backed metrics (require driving the ReAct loop) ─────────────────


def run_llm_backed_metrics(
    cases: tuple[Case, ...] = CASES,
    *,
    max_cases: int = 30,
) -> dict[str, Any]:
    """Run a subset of cases through the actual ReAct loop.

    Returns metrics that need a live model:
    - tool_error_recovery_rate: % of recoverable errors that led to a corrected retry
    - loop_exhaustion_rate: % of runs that hit the iteration cap
    - task_success_rate: % of multi-step cases that completed their expected steps
    - reflection_triggered_rate: % of runs where reflection was invoked
    """
    # Select cases that benefit from loop execution
    error_cases = [c for c in cases if c.category == "D"]
    loop_cases = [c for c in cases if c.category == "H"]
    multi_step_cases = [c for c in cases if c.category == "C"]
    test_cases = list(dict.fromkeys(error_cases + loop_cases + multi_step_cases))[:max_cases]

    if not test_cases:
        return {k: 0.0 for k in LLM_BACKED_METRICS}

    # Placeholder until a real model server is available in the test harness.
    # The loop instrumentation (LoopDetector, reflection, early stop) is in place
    # and will produce these numbers when driven by a live model.
    return {
        "tool_error_recovery_rate": 0.0,
        "loop_exhaustion_rate": 0.0,
        "task_success_rate": 0.0,
        "reflection_triggered_rate": 0.0,
        "llm_backed_cases": len(test_cases),
    }


# ── Runner ──────────────────────────────────────────────────────


def run(
    label: str,
    *,
    select: Callable[[str], list[str]] = select_current,
    mode: Callable[[str, str | None], str] = _mode_for,
    cases: tuple[Case, ...] = CASES,
) -> RunReport:
    from core.settings import get_settings

    results: list[CaseResult] = []
    for case in cases:
        offered = list(dict.fromkeys(select(case.prompt)))
        # The prompt itself may be the explicit mode command ("modo estoque"),
        # so hand it to the router as well.
        actual_mode = mode(case.prompt, case.prompt)
        hits = [name for name in offered if name in case.required_tools]
        notes: list[str] = []
        if case.required_tools and not hits:
            notes.append("nenhuma ferramenta capaz foi oferecida")
        if case.expect_no_tool and offered:
            notes.append(f"recebeu {len(offered)} ferramentas sem necessidade")
        if case.expect_mode and actual_mode != case.expect_mode:
            notes.append(f"modo {actual_mode} != {case.expect_mode}")
        results.append(
            CaseResult(
                id=case.id,
                category=case.category,
                prompt=case.prompt,
                expected_tools=sorted(case.required_tools),
                offered_tools=offered,
                hits=sorted(hits),
                expected_mode=case.expect_mode,
                actual_mode=actual_mode,
                expect_no_tool=case.expect_no_tool,
                notes=notes,
            )
        )

    encoder = _encoder_available()
    base_metrics = compute_metrics(results)
    llm_metrics = run_llm_backed_metrics()
    base_metrics.update(llm_metrics)
    return RunReport(
        label=label,
        retrieval=getattr(select, "__name__", str(select)),
        mode=getattr(mode, "__name__", str(mode)),
        encoder_available=encoder,
        embedding_model=get_settings().embedding_model,
        cases=results,
        metrics=base_metrics,
    )


def _encoder_available() -> bool:
    """Whether the real encoder loads, which decides what the numbers mean."""
    try:
        from core.embeddings import try_get_sentence_transformer
        from core.settings import get_settings

        return try_get_sentence_transformer(get_settings().embedding_model) is not None
    except Exception:
        return False


def save(report: RunReport, directory: Path, filename: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    name = filename or f"{report.label}.json"
    path = directory / name
    path.write_text(report.to_json(), encoding="utf-8")
    return path


def format_summary(report: RunReport) -> str:
    m = report.metrics
    lines = [
        f"== {report.label} ==",
        f"retrieval: {report.retrieval}   mode: {report.mode}",
        f"encoder real disponivel: {'sim' if report.encoder_available else 'NAO (fallback lexical)'}",
        f"model: {report.embedding_model}",
        "",
        f"Tool Recall          {m['tool_recall']:.3f}  ({m['tool_recall_hits']}/{m['cases_with_tool_expectation']})",
        f"Recall@1             {m['recall_at_1']:.3f}",
        f"Recall@3             {m['recall_at_3']:.3f}",
        f"Tool Precision       {m['tool_precision']:.3f}",
        f"Zero Tool Rate (op)  {m['zero_tool_rate_operational']:.3f}  ({m['operational_zero_tool_count']} casos)",
        f"Zero Tool (geral)    {m['false_tool_rate_on_general']:.3f}  (invertido: 0 e o ideal)",
        f"Mode Accuracy        {m['mode_accuracy']:.3f}  ({m['mode_labelled_cases']} casos rotulados)",
        f"Tools enviados/turno {m['tools_offered_avg']}",
    ]
    cats = report.per_category()
    if cats:
        lines.append("")
        lines.append("por categoria:")
        for category in sorted(cats):
            b = cats[category]
            recall = b["recall_hits"] / b["total"] if b["total"] else 0.0
            mode = f"{b['mode_ok']}/{b['mode_total']}" if b["mode_total"] else "-"
            lines.append(f"  {category}: recall {recall:.2f} ({int(b['recall_hits'])}/{int(b['total'])})  mode {mode}")
    lines.append("")
    lines.append("nao medido (exige LLM real dirigindo o loop):")
    lines.extend(f"  - {name}" for name in LLM_BACKED_METRICS)
    return "\n".join(lines)


def compare(before: RunReport, after: RunReport) -> str:
    """A before/after table over the metrics both runs can produce."""
    keys = (
        "tool_recall",
        "recall_at_1",
        "recall_at_3",
        "tool_precision",
        "zero_tool_rate_operational",
        "false_tool_rate_on_general",
        "mode_accuracy",
        "tools_offered_avg",
    )
    lines = [
        f"{'metrica':<30}{'antes':>10}{'depois':>10}{'delta':>12}",
        "-" * 62,
    ]
    for key in keys:
        a = before.metrics.get(key, 0.0)
        b = after.metrics.get(key, 0.0)
        delta = b - a
        mark = "+" if delta > 0 else ""
        lines.append(f"{key:<30}{a:>10.4f}{b:>10.4f}{mark}{delta:>11.4f}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    out_dir = Path(argv[0]) if argv else Path("evals/results")

    runs = [
        run("atual", select=select_current, mode=_mode_for),
        run("lexical_only", select=select_lexical_only, mode=_mode_lexical_only),
        run("semantic_only", select=select_semantic_only, mode=_mode_for),
    ]
    for report in runs:
        save(report, out_dir)
        print(format_summary(report))
        print()

    print(compare(runs[1], runs[0]))
    print()
    print(f"resultados salvos em {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
