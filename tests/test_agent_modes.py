"""Contracts for the agentic modes and the task state vocabulary.

Modes are the product's main safety boundary for autonomy, so these tests pin:

* the six required modes exist and are selectable by id, label and alias;
* every tool a mode allows actually exists in the tool catalog;
* a mode that can write still keeps ``confirm_before_write`` on;
* limits are clamped by the global ceilings;
* the task state vocabulary is closed, and legacy checkpoints are normalized.
"""

from __future__ import annotations

import pytest

from core.agent_modes import (
    DEFAULT_MODE_ID,
    MODES,
    MODES_BY_ID,
    detect_mode,
    filter_tools,
    get_mode,
    is_tool_allowed,
    is_valid_mode,
    list_modes,
    parse_mode_command,
    tools_for_mode,
)
from core.agent_tasks import (
    RESUMABLE_STATES,
    TASK_STATES,
    TERMINAL_STATES,
    AgentTaskStore,
    is_resumable,
    is_terminal,
    normalize_state,
)
from core.settings import AgentModeSettings

REQUIRED_MODE_IDS = {
    "assistente",
    "executor",
    "documentos",
    "estoque",
    "pesquisador",
    "desenvolvedor",
}


class TestModes:
    def test_the_six_required_modes_exist(self) -> None:
        assert set(MODES_BY_ID) >= REQUIRED_MODE_IDS

    def test_catalog_is_serializable_and_unique(self) -> None:
        catalog = list_modes()
        ids = [entry["id"] for entry in catalog]
        assert len(ids) == len(set(ids))
        assert set(ids) == set(MODES_BY_ID)
        for entry in catalog:
            assert entry["label"] and entry["summary"] and entry["prompt"]
            assert isinstance(entry["tools"], list)

    def test_every_allowed_tool_exists_in_the_catalog(self) -> None:
        from ai.tools import REGISTRO_FERRAMENTAS

        known = {f.nome for f in REGISTRO_FERRAMENTAS}
        for mode in MODES:
            unknown = [t for t in mode.tools if t not in known]
            assert unknown == [], f"modo {mode.id} referencia ferramentas inexistentes: {unknown}"

    def test_modes_that_write_still_require_confirmation(self) -> None:
        from core.tool_policy import assess_tool

        for mode in MODES:
            if not mode.confirm_before_write:
                pytest.fail(f"modo {mode.id} nao pode desligar a confirmacao de escrita")
            for tool in mode.tools:
                if assess_tool(tool).risk.value in {
                    "write",
                    "destructive",
                    "external",
                    "irreversible",
                }:
                    assert assess_tool(tool).requires_confirmation is True

    def test_only_planning_modes_can_plan(self) -> None:
        assert MODES_BY_ID["assistente"].can_plan is False
        for mode_id in ("executor", "documentos", "estoque", "pesquisador", "desenvolvedor"):
            assert MODES_BY_ID[mode_id].can_plan is True

    def test_web_tools_are_restricted_to_modes_that_declare_network(self) -> None:
        web = {
            "pesquisar_web",
            "pesquisar_google",
            "pesquisar_noticias",
            "navegar_web",
            "abrir_no_navegador",
        }
        for mode in MODES:
            if mode.allows("pesquisar_web"):
                assert mode.network, f"modo {mode.id} usa web sem declarar network"

    def test_resolver_accepts_id_label_and_unknown(self) -> None:
        assert get_mode("executor").id == "executor"
        assert get_mode("EXECUTOR").id == "executor"
        assert get_mode("Executor").id == "executor"
        assert get_mode(None).id == DEFAULT_MODE_ID
        assert get_mode("modo-que-nao-existe").id == DEFAULT_MODE_ID

    def test_is_valid_mode_does_not_guess(self) -> None:
        assert is_valid_mode("estoque") is True
        assert is_valid_mode("Estoque") is False
        assert is_valid_mode("nope") is False

    def test_limits_are_clamped_by_the_global_ceilings(self) -> None:
        mode = MODES_BY_ID["executor"]
        ceiling = AgentModeSettings(max_steps=8, max_iterations=5, max_seconds=60, max_attempts=1)
        limits = mode.limits(
            ceiling_steps=ceiling.max_steps,
            ceiling_seconds=ceiling.max_seconds,
            ceiling_attempts=ceiling.max_attempts,
            ceiling_iterations=ceiling.max_iterations,
        )
        assert limits == {
            "max_steps": 8,
            "max_iterations": 5,
            "max_seconds": 60,
            "max_attempts": 1,
        }

    def test_limits_fall_back_to_the_mode_when_ceilings_are_higher(self) -> None:
        mode = MODES_BY_ID["documentos"]
        limits = mode.limits(
            ceiling_steps=mode.max_steps + 100,
            ceiling_seconds=mode.max_seconds + 100,
            ceiling_attempts=mode.max_attempts + 3,
            ceiling_iterations=mode.max_iterations + 100,
        )
        assert limits == {
            "max_steps": mode.max_steps,
            "max_iterations": mode.max_iterations,
            "max_seconds": mode.max_seconds,
            "max_attempts": mode.max_attempts,
        }

    def test_a_document_mode_budgets_turns_apart_from_tool_calls(self) -> None:
        # A document batch writes prose in most of its turns, so a shared budget
        # would stop it before it reached the end of the work.
        mode = MODES_BY_ID["documentos"]
        assert mode.max_iterations > mode.max_steps

    def test_tool_helpers(self) -> None:
        assert is_tool_allowed("estoque", "saida_estoque") is True
        assert is_tool_allowed("documentos", "saida_estoque") is False
        assert "listar_estoque" in tools_for_mode("estoque")

    def test_filter_tools_preserves_order_and_drops_the_rest(self) -> None:
        from types import SimpleNamespace

        tools = [
            SimpleNamespace(nome=n) for n in ("buscar_web", "listar_estoque", "executar_codigo")
        ]
        kept = [t.nome for t in filter_tools("estoque", tools)]
        assert kept == ["listar_estoque"]

    def test_detect_mode_returns_none_when_nothing_matches(self) -> None:
        assert detect_mode("quero saber o saldo da conta") is None


class TestModeCommands:
    """Voice/phone orders must switch the mode without reaching the model."""

    def test_explicit_prefixes_resolve_to_a_mode(self) -> None:
        assert parse_mode_command("modo estoque") == "estoque"
        assert parse_mode_command("Mudar modo para documentos") == "documentos"
        assert parse_mode_command("trocar modo researcher") == "pesquisador"

    def test_a_trailing_request_is_still_a_switch(self) -> None:
        assert parse_mode_command("modo estoque e me diga o total") == "estoque"

    def test_ordinary_questions_are_not_switch_commands(self) -> None:
        assert parse_mode_command("qual o total do estoque?") is None
        assert parse_mode_command("modo") is None
        assert parse_mode_command("modo desconhecido") is None
        assert parse_mode_command("") is None


class TestTaskStateVocabulary:
    def test_the_eight_required_states_exist(self) -> None:
        assert set(TASK_STATES) == {
            "created",
            "planning",
            "waiting_confirmation",
            "running",
            "paused",
            "cancelled",
            "failed",
            "completed",
        }

    def test_terminal_and_resumable_do_not_overlap(self) -> None:
        # ``cancelled`` is both: terminal for the scheduler (it is not running)
        # and resumable for the user (an explicit RETOMAR may continue it).
        assert {"cancelled"} == TERMINAL_STATES & RESUMABLE_STATES

    def test_a_spent_budget_is_not_resumable(self) -> None:
        """RETOMAR on a failed task only reports it; it must never replay."""
        assert is_terminal("failed") is True
        assert is_resumable("failed") is False

    def test_legacy_states_are_normalized(self) -> None:
        assert normalize_state("awaiting_approval") == "waiting_confirmation"
        assert normalize_state("needs_review") == "paused"
        assert normalize_state("blocked") == "paused"
        assert normalize_state("Awaiting_Approval") == "waiting_confirmation"

    def test_unknown_state_falls_back_to_paused_not_running(self) -> None:
        """An unrecognized state must never be interpreted as 'keep going'."""
        assert normalize_state("lixo") == "paused"
        assert normalize_state("") == "paused"
        assert is_terminal("lixo") is False
        assert is_resumable("lixo") is True

    def test_completed_is_terminal_and_not_resumable(self) -> None:
        assert is_terminal("completed") is True
        assert is_resumable("completed") is False

    def test_store_creates_a_created_task_with_a_mode(self, tmp_path) -> None:
        store = AgentTaskStore(tmp_path / "tasks.db")
        task = store.create("conversa", {"pergunta": "faça o relatorio"}, mode="estoque")
        assert task["status"] == "created"
        assert task["mode"] == "estoque"
        assert store.get(task["id"], "conversa")["status"] == "created"

    def test_store_falls_back_to_a_valid_mode(self, tmp_path) -> None:
        store = AgentTaskStore(tmp_path / "tasks.db")
        task = store.create("conversa", {"pergunta": "oi"}, mode="modo-inexistente")
        assert task["mode"] == DEFAULT_MODE_ID

    def test_store_normalizes_a_legacy_row_on_read(self, tmp_path) -> None:
        """A checkpoint written by an older build is readable, not confusing."""
        import json
        import time

        from core.sqlite_store import connect

        store = AgentTaskStore(tmp_path / "tasks.db")
        legacy = {
            "id": "legacy123",
            "scope": "conversa",
            "status": "awaiting_approval",
            "objective": "tarefa antiga",
            "prompt": {"pergunta": "tarefa antiga"},
            "messages": [],
            "steps": [{"approval_code": "ABC123", "status": "awaiting_approval"}],
            "iterations": 1,
            "result": "",
            "error": "",
            "created": time.time(),
            "updated": time.time(),
        }
        with connect(store.path) as db:
            db.execute(
                "INSERT INTO agent_tasks VALUES (?, ?, ?, ?)",
                (
                    legacy["id"],
                    legacy["scope"],
                    legacy["updated"],
                    json.dumps(legacy, ensure_ascii=False),
                ),
            )

        task = store.get("legacy123", "conversa")
        assert task is not None
        assert task["status"] == "waiting_confirmation"
        # A pending approval must still be findable under the new vocabulary.
        assert store.find_approval("ABC123", "conversa") is not None

    def test_save_normalizes_the_status(self, tmp_path) -> None:
        store = AgentTaskStore(tmp_path / "tasks.db")
        task = store.create("conversa", {"pergunta": "oi"})
        task["status"] = "needs_review"
        store.save(task)
        assert store.get(task["id"], "conversa")["status"] == "paused"
