"""Standalone golden-set test runner - runs in fresh process without pytest/conftest."""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from evals import harness
from evals.cases import CASES, by_category

READ_CORE = {"buscar_item_estoque", "buscar_memoria", "informacoes_sistema", "listar_estoque"}


def run_current() -> harness.RunReport:
    return harness.run("atual")


def run_lexical() -> harness.RunReport:
    return harness.run("lexical_only", mode=harness._mode_lexical_only)


def test_tool_recall_does_not_regress():
    assert run_current().metrics["tool_recall"] >= 0.85
    print("PASS: test_tool_recall_does_not_regress")


def test_zero_tool_rate_does_not_regress():
    assert run_current().metrics["zero_tool_rate_operational"] <= 0.10
    print("PASS: test_zero_tool_rate_does_not_regress")


def test_mode_accuracy_does_not_regress():
    assert run_current().metrics["mode_accuracy"] >= 0.85
    print("PASS: test_mode_accuracy_does_not_regress")


def test_general_questions_stay_tool_free():
    assert run_current().metrics["false_tool_rate_on_general"] <= 0.40
    print("PASS: test_general_questions_stay_tool_free")


def test_semantic_layer_never_adds_tools_to_general_questions():
    lexical_only = harness.run("probe", select=harness.select_lexical_only)
    lexical_by_id = {c.id: set(c.offered_tools) for c in lexical_only.cases}

    for case in run_current().cases:
        if not case.expect_no_tool:
            continue
        assert set(case.offered_tools) == lexical_by_id[case.id], (
            f"{case.id} ('{case.prompt}') received tools lexical didn't give: "
            f"{sorted(set(case.offered_tools) - lexical_by_id[case.id])}"
        )
    print("PASS: test_semantic_layer_never_adds_tools_to_general_questions")


def test_floor_never_reaches_a_general_question():
    from ai import react as ai_react
    from ai import tool_retrieval

    def floor_fires(prompt: str) -> bool:
        selected = ai_react._expandir_ferramentas_por_semantica(prompt, set())
        return bool(READ_CORE & selected)

    for prompt in (
        "qual a diferen\u00e7a entre lista e tupla em Python?",
        "me explique um algoritmo de ordena\u00e7\u00e3o",
        "gere um relat\u00f3rio com o que voc\u00ea sabe sobre Python",
        "quero um gr\u00e1fico bonito",
        "o que \u00e9 um script?",
    ):
        assert not floor_fires(prompt), f"floor fired for topic: {prompt!r}"
        assert not tool_retrieval.asks_about_local_data(prompt), prompt

    for prompt in (
        "quais componentes temos",
        "quais documentos eu tenho",
        "meus clientes",
        "qual o estoque de parafusos",
    ):
        assert floor_fires(prompt), f"floor didn't fire for local data: {prompt!r}"
    print("PASS: test_floor_never_reaches_a_general_question")


def test_lexical_matches_are_never_dropped():
    lexical_by_id = {c.id: set(c.offered_tools) for c in run_lexical().cases}
    for case in run_current().cases:
        missing = lexical_by_id[case.id] - set(case.offered_tools)
        assert not missing, f"{case.id} lost {sorted(missing)}"
    print("PASS: test_lexical_matches_are_never_dropped")


def test_broad_tool_flood_is_controlled():
    assert run_current().metrics["tools_offered_avg"] <= 6.0
    print("PASS: test_broad_tool_flood_is_controlled")


def test_semantic_layer_is_not_silently_inert():
    import sys as _sys

    lexical_only = run_lexical()
    lexical_by_id = {c.id: set(c.offered_tools) for c in lexical_only.cases}

    real_gains = []
    for case in run_current().cases:
        extra = set(case.offered_tools) - lexical_by_id[case.id]
        real_gains.extend(extra & set(case.expected_tools))

    print(f"DEBUG: real_gains={len(real_gains)}", file=_sys.stderr)
    if real_gains:
        print(f"DEBUG: gains sample={real_gains[:5]}", file=_sys.stderr)
    assert real_gains, (
        "no capable tool came from semantic retrieval: encoder is inert and "
        "current gain is only READ_CORE floor"
    )
    print("PASS: test_semantic_layer_is_not_silently_inert")


def test_paraphrases_are_not_solved_by_keywords():
    paraphrases = {c.id for c in by_category("E")}
    hits = [c for c in run_current().cases if c.id in paraphrases and c.recall_hit]

    assert len(hits) / len(paraphrases) >= 0.7, (
        f"only {len(hits)}/{len(paraphrases)} paraphrases hit a capable tool; "
        "semantic retrieval inactive"
    )
    print("PASS: test_paraphrases_are_not_solved_by_keywords")


def test_baseline_is_recorded_with_its_measurement_path():
    report = harness.run("probe")
    assert isinstance(report.encoder_available, bool)
    assert report.embedding_model
    print("PASS: test_baseline_is_recorded_with_its_measurement_path")


def test_every_case_has_a_category_and_prompt():
    assert len(CASES) >= 50
    for case in CASES:
        assert case.prompt.strip()
        assert case.category in set("ABCDEFGH")
    print("PASS: test_every_case_has_a_category_and_prompt")


def test_ids_are_unique():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids))
    print("PASS: test_ids_are_unique")


def test_every_required_tool_exists_in_the_registry():
    from ai.tools import REGISTRO_FERRAMENTAS

    known = {t.nome for t in REGISTRO_FERRAMENTAS}
    for case in CASES:
        unknown = set(case.required_tools) - known
        assert not unknown, f"{case.id} requires non-existent tools: {unknown}"
    print("PASS: test_every_required_tool_exists_in_the_registry")


def test_expect_mode_is_a_real_mode():
    from core.agent_modes import MODES

    known = {m.id for m in MODES}
    for case in CASES:
        if case.expect_mode:
            assert case.expect_mode in known, f"{case.id}: mode {case.expect_mode} unknown"
    print("PASS: test_expect_mode_is_a_real_mode")


def test_no_tool_cases_expect_no_tools():
    for case in CASES:
        if case.expect_no_tool:
            assert not case.required_tools, f"{case.id} contradicts itself"
    print("PASS: test_no_tool_cases_expect_no_tools")


if __name__ == "__main__":
    tests = [
        test_every_case_has_a_category_and_prompt,
        test_ids_are_unique,
        test_every_required_tool_exists_in_the_registry,
        test_expect_mode_is_a_real_mode,
        test_no_tool_cases_expect_no_tools,
        test_tool_recall_does_not_regress,
        test_zero_tool_rate_does_not_regress,
        test_mode_accuracy_does_not_regress,
        test_general_questions_stay_tool_free,
        test_semantic_layer_never_adds_tools_to_general_questions,
        test_floor_never_reaches_a_general_question,
        test_lexical_matches_are_never_dropped,
        test_broad_tool_flood_is_controlled,
        test_semantic_layer_is_not_silently_inert,
        test_paraphrases_are_not_solved_by_keywords,
        test_baseline_is_recorded_with_its_measurement_path,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed.append(test.__name__)
        except Exception as e:
            print(f"ERROR: {test.__name__}: {e}")
            failed.append(test.__name__)

    print(f"\n{'=' * 50}")
    print(f"Results: {len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        print(f"Failed: {failed}")
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)
