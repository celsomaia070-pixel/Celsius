"""Golden-set regression gate.

These assertions are **floors, not targets**. They encode the measured baseline
so a future change cannot quietly lose capability. They deliberately do not
assert the metrics an inert encoder cannot move â€” asserting those would only
lock in the current failure.

Two tests here are the important ones:

* ``test_paraphrases_are_not_solved_by_keywords`` fails while the encoder is
  dead, and passes once it works. That is the honest encoding of "Fase 1 is not
  yet effective".
* ``test_semantic_layer_is_not_silently_inert`` names the blocker directly, so
  the suite cannot go green while tool retrieval is only _lexical().
"""

from __future__ import annotations

import pytest

from evals import harness
from evals.cases import CASES, by_category

READ_CORE = {"buscar_item_estoque", "buscar_memoria", "informacoes_sistema", "listar_estoque"}


def _current() -> harness.RunReport:
    # Force fresh imports and reset all module-level caches
    import importlib
    import evals.harness
    importlib.reload(evals.harness)
    import ai.tool_retrieval as tr_mod
    importlib.reload(tr_mod)
    import ai.react as ai_react_mod
    importlib.reload(ai_react_mod)
    # Reset module-level caches
    import ai.tool_retrieval as tr
    tr._embeddings.clear()
    tr._embeddings_model = None
    tr._model_loaded = False
    import ai.react as ai_react
    if hasattr(ai_react, '_filtrar_ferramentas_cache'):
        ai_react._filtrar_ferramentas_cache.clear()
    import evals.harness as harness_mod
    return harness_mod.run("atual")


def _lexical() -> harness.RunReport:
    return harness.run("lexical_only", mode=harness._mode_lexical_only)


# â”€â”€ Dataset integrity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Guards the labels themselves. A golden set with wrong expectations produces
# confident nonsense, so this is checked before any metric is trusted.


def test_every_case_has_a_category_and_prompt():
    assert len(CASES) >= 50, "a spec pede 50-60 prompts como base"
    for case in CASES:
        assert case.prompt.strip()
        assert case.category in set("ABCDEFGH")


def test_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))


def test_every_required_tool_exists_in_the_registry():
    from ai.tools import REGISTRO_FERRAMENTAS

    known = {t.nome for t in REGISTRO_FERRAMENTAS}
    for case in CASES:
        unknown = set(case.required_tools) - known
        assert not unknown, f"{case.id} exige ferramentas inexistentes: {unknown}"


def test_expect_mode_is_a_real_mode():
    from core.agent_modes import MODES

    known = {m.id for m in MODES}
    for case in CASES:
        if case.expect_mode:
            assert case.expect_mode in known, f"{case.id}: modo {case.expect_mode} inexistente"


def test_no_tool_cases_expect_no_tools():
    # Otherwise a case would assert "no tool" and simultaneously penalise the
    # very tools it lists as required.
    for case in CASES:
        if case.expect_no_tool:
            assert not case.required_tools, f"{case.id} contradiz a si mesmo"


# â”€â”€ Floors from the measured baseline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_tool_recall_does_not_regress():
    assert _current().metrics["tool_recall"] >= 0.90


def test_zero_tool_rate_does_not_regress():
    assert _current().metrics["zero_tool_rate_operational"] <= 0.05


def test_mode_accuracy_does_not_regress():
    assert _current().metrics["mode_accuracy"] >= 0.85


def test_general_questions_stay_tool_free():
    # Known pre-existing false positive, tracked as a floor rather than a goal.
    #
    # F04 ("qual a diferenca entre lista e tupla em Python?") matches the
    # literal keyword "python", registered on both ``executar_codigo``
    # (ai/react.py:1522) and ``informacoes_sistema`` (ai/react.py:1577). This is
    # a property of the *original* keyword map, not of the semantic layer.
    # Separating "execute this Python code" from "explain a Python concept" needs
    # intent, which is what the encoder is for; widening or trimming the keyword
    # list here would trade one regression for another.
    assert _current().metrics["false_tool_rate_on_general"] <= 0.091, (
        "Falso positivo novo em pergunta geral. Se este numero subiu, a causa "
        "provavelmente e o piso READ_CORE e nao o mapa _lexical()."
    )


def test_semantic_layer_never_adds_tools_to_general_questions():
    """The invariant that actually matters, and the one the floor broke.

    A general-knowledge question must get exactly what the lexical path gave
    it. Anything more means the semantic layer or the ``READ_CORE`` floor
    invented a need the user did not express.
    """
    lexical_only = harness.run("probe", select=harness.select_lexical_only)
    lexical_by_id = {c.id: set(c.offered_tools) for c in lexical_only.cases}

    for case in _current().cases:
        if not case.expect_no_tool:
            continue
        assert set(case.offered_tools) == lexical_by_id[case.id], (
            f"{case.id} ('{case.prompt}') recebeu ferramentas que o caminho "
            f"lexical nao dava: {sorted(set(case.offered_tools) - lexical_by_id[case.id])}"
        )


def test_floor_never_reaches_a_general_question():
    """``READ_CORE`` must be earned by a local-data noun, never a topic word.

    Asserted on the floor function itself rather than on the final tool set,
    because a general question can still receive a tool from the keyword map
    (F04 matches the literal keyword "python") and that would be indistinguishable
    from the floor firing.
    """
    from ai import react as ai_react
    from ai import tool_retrieval

    def floor_fires(prompt: str) -> bool:
        selected = ai_react._expandir_ferramentas_por_semantica(prompt, set())
        return bool(READ_CORE & selected)

    # Topic words: enough to open the gate, not enough to earn the floor.
    for prompt in (
        "qual a diferenÃ§a entre lista e tupla em Python?",
        "me explique um algoritmo de ordenaÃ§Ã£o",
        "gere um relatÃ³rio com o que vocÃª sabe sobre Python",
        "quero um grÃ¡fico bonito",
        "o que Ã© um script?",
    ):
        assert not floor_fires(prompt), f"piso disparou para_topico: {prompt!r}"
        # The gate may still be open; that is fine, retrieval just proposes.
        assert not tool_retrieval.asks_about_local_data(prompt), prompt

    # Local-data nouns: the floor is exactly the point.
    for prompt in (
        "quais componentes temos",
        "quais documentos eu tenho",
        "meus clientes",
        "qual o estoque de parafusos",
    ):
        assert floor_fires(prompt), f"piso nao disparou para dados locais: {prompt!r}"


def test_lexical_matches_are_never_dropped():
    # The hybrid must be a superset of the lexical result, case by case. This is
    # the regression that matters for "esconder ferramentas anteriormente
    # funcionais".
    lexical_by_id = {c.id: set(c.offered_tools) for c in _lexical().cases}
    for case in _current().cases:
        missing = lexical_by_id[case.id] - set(case.offered_tools)
        assert not missing, f"{case.id} perdeu {sorted(missing)}"


def test_broad_tool_flood_is_controlled():
    # A hard ceiling on what a single turn may carry, so precision cannot rot
    # silently as the registry grows.
    assert _current().metrics["tools_offered_avg"] <= 4.0


# â”€â”€ The blocker, named â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_semantic_layer_is_not_silently_inert():
    """Fails while the embedding model cannot be loaded.

    ``atual`` must offer at least one tool that the lexical path alone does not,
    and it must be a real capability hit. Today every extra tool comes from the
    ``READ_CORE`` floor, so this fails — which is the point: the suite refuses to
    report Fase 1 as working while the encoder is dead.
    """
    import sys
    # Run lexical only to compare
    lexical_only = _lexical()
    lexical_by_id = {c.id: set(c.offered_tools) for c in lexical_only.cases}

    real_gains = []
    for case in _current().cases:
        extra = set(case.offered_tools) - lexical_by_id[case.id]
        real_gains.extend(extra & set(case.expected_tools))

    print(f"DEBUG: real_gains={len(real_gains)}", file=sys.stderr)
    if real_gains:
        print(f"DEBUG: gains sample={real_gains[:5]}", file=sys.stderr)
    # With encoder active, we should have significant real gains
    assert real_gains, (
        "nenhuma ferramenta capaz veio do retrieval semantico: o encoder esta inerte e o ganho atual e "
        "apenas o piso READ_CORE"
    )


def test_paraphrases_are_not_solved_by_keywords():
    """Category E is the discriminator for semantic retrieval.

    If these pass with keywords alone, the semantic layer is not being
    exercised and the metrics are measuring the wrong thing.
    """
    paraphrases = {c.id for c in by_category("E")}
    hits = [c for c in _current().cases if c.id in paraphrases and c.recall_hit]

    # With semantic retrieval active, expect high hit rate on paraphrases
    assert len(hits) / len(paraphrases) >= 0.7, (
        f"apenas {len(hits)}/{len(paraphrases)} parafrases chegaram a uma "
        "ferramenta capaz; retrieval semantico inativo"
    )


def test_baseline_is_recorded_with_its_measurement_path():
    # A report without its encoder state is not comparable to anything.
    report = harness.run("probe")
    assert isinstance(report.encoder_available, bool)
    assert report.embedding_model
