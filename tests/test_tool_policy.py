"""Contracts for the deterministic tool policy and the Jev-probabilistic guard.

These tests pin the safety invariants the product depends on:

* reads run without confirmation;
* writes, deletions, external and irreversible actions always require it;
* an unknown tool fails closed;
* Jev can only *add* a confirmation, never remove one;
* every real tool in ``ai.tools`` has a declared policy (otherwise "fail closed"
  would silently turn every call into an approval prompt).
"""

from __future__ import annotations

import pytest

from core.decisions import DecisionClient, DecisionProvider, evaluate_tool_call
from core.settings import DecisionLayerSettings
from core.tool_approval import SENSITIVE_TOOLS
from core.tool_policy import (
    CONFIRMING_RISKS,
    Risk,
    allowed_tools_without_confirmation,
    assess_tool,
    is_read_only,
    policy_table,
    summarize_arguments,
)


class TestRiskAssessment:
    @pytest.mark.parametrize(
        "tool",
        [
            "listar_estoque",
            "buscar_item_estoque",
            "buscar_memoria",
            "listar_documentos_rag",
            "informacoes_sistema",
        ],
    )
    def test_reads_need_no_confirmation(self, tool: str) -> None:
        verdict = assess_tool(tool)
        assert verdict.requires_confirmation is False
        assert verdict.risk is Risk.READ
        assert is_read_only(tool)

    @pytest.mark.parametrize(
        "tool",
        [
            "saida_estoque",
            "entrada_estoque",
            "adicionar_item_estoque",
            "cadastrar_cliente",
            "salvar_memoria",
            "remover_documento",
            "criar_editar_arquivo",
            "executar_codigo",
            "abrir_no_navegador",
        ],
    )
    def test_mutating_and_external_tools_require_confirmation(self, tool: str) -> None:
        verdict = assess_tool(tool)
        assert verdict.requires_confirmation is True
        assert verdict.risk in CONFIRMING_RISKS

    @pytest.mark.parametrize("tool", ["gerar_relatorio_local", "gerar_grafico"])
    def test_generating_a_new_file_is_not_a_destructive_write(self, tool: str) -> None:
        """These always create a new file in a managed folder; they never overwrite."""
        verdict = assess_tool(tool)
        assert verdict.requires_confirmation is False
        assert verdict.risk is Risk.DERIVED

    @pytest.mark.parametrize(
        "tool", ["pesquisar_web", "pesquisar_google", "pesquisar_noticias", "navegar_web"]
    )
    def test_public_network_reads_are_authorized_by_research_intent(self, tool: str) -> None:
        verdict = assess_tool(tool)
        assert verdict.requires_confirmation is False
        assert verdict.risk is Risk.READ

    def test_unknown_tool_fails_closed(self) -> None:
        verdict = assess_tool("ferramenta_que_nao_existe")
        assert verdict.requires_confirmation is True
        assert verdict.risk is Risk.UNKNOWN
        assert verdict.policy_known is False

    def test_dual_use_tool_escalates_on_its_irreversible_argument(self) -> None:
        # Executing code is only really dangerous with a payload attached.
        assert assess_tool("executar_codigo").requires_confirmation is True

    def test_existing_sensitive_allowlist_can_only_tighten(self) -> None:
        """Every legacy SENSITIVE_TOOLS entry must still require confirmation."""
        offenders = [t for t in SENSITIVE_TOOLS if not assess_tool(t).requires_confirmation]
        assert offenders == []

    def test_policy_table_is_serializable_and_sorted(self) -> None:
        entries = policy_table().as_list()
        assert entries == sorted(entries, key=lambda e: e["tool"])
        assert all({"tool", "risk", "requires_confirmation", "reason"} <= set(e) for e in entries)

    def test_read_only_allowlist_contains_no_confirming_tool(self) -> None:
        allowed = allowed_tools_without_confirmation()
        assert "listar_estoque" in allowed
        assert not allowed & SENSITIVE_TOOLS

    def test_argument_summary_is_bounded(self) -> None:
        summary = summarize_arguments({"texto": "x" * 5000})
        assert len(summary) <= 300
        assert summary.endswith("...")
        assert summarize_arguments(None) == "{}"


class TestEvaluateToolCall:
    def test_disabled_layer_applies_policy_only(self) -> None:
        settings = DecisionLayerSettings(enabled=False)
        client = DecisionClient(settings, provider=DecisionProvider())

        write = evaluate_tool_call(client, settings, tool="saida_estoque", arguments={})
        read = evaluate_tool_call(client, settings, tool="listar_estoque", arguments={})

        assert write.requires_confirmation is True
        assert write.source == "policy"
        assert read.requires_confirmation is False

    def test_disabled_layer_never_calls_the_provider(self) -> None:
        class BoomProvider(DecisionProvider):
            def decide(self, request, *, timeout_ms):  # pragma: no cover - must not run
                raise AssertionError("provider must not run when the layer is off")

        settings = DecisionLayerSettings(enabled=False)
        client = DecisionClient(settings, provider=BoomProvider())
        assert (
            evaluate_tool_call(client, settings, tool="listar_estoque").requires_confirmation
            is False
        )

    def test_jev_can_add_a_confirmation_to_a_read(self) -> None:
        """Monotonicity: the probabilistic layer may only ever be stricter."""
        from core.decisions import NoulAnswer

        settings = DecisionLayerSettings(enabled=True)

        class RiskyProvider(DecisionProvider):
            def decide(self, request, *, timeout_ms):
                return {qid: NoulAnswer(noul=0.9) for qid in request.questions}

        client = DecisionClient(settings, provider=RiskyProvider())
        verdict = evaluate_tool_call(client, settings, tool="listar_estoque")
        assert verdict.requires_confirmation is True
        assert verdict.policy_requires_confirmation is False
        assert verdict.source == "jev"
        assert verdict.probability == pytest.approx(0.9)

    def test_jev_never_releases_a_policy_confirmation(self) -> None:
        from core.decisions import NoulAnswer

        settings = DecisionLayerSettings(enabled=True)

        class SafeProvider(DecisionProvider):
            def decide(self, request, *, timeout_ms):
                return {qid: NoulAnswer(noul=0.0) for qid in request.questions}

        client = DecisionClient(settings, provider=SafeProvider())
        verdict = evaluate_tool_call(client, settings, tool="remover_documento")
        assert verdict.requires_confirmation is True
        assert verdict.source == "policy"

    def test_decision_server_outage_keeps_the_deterministic_guard(self) -> None:
        settings = DecisionLayerSettings(enabled=True, provider="local")

        class DownProvider(DecisionProvider):
            def decide(self, request, *, timeout_ms):
                return None  # transport failure

        client = DecisionClient(settings, provider=DownProvider())
        write = evaluate_tool_call(client, settings, tool="saida_estoque", arguments={})
        read = evaluate_tool_call(client, settings, tool="listar_estoque", arguments={})
        assert write.requires_confirmation is True
        assert read.requires_confirmation is False

    def test_verdict_is_serializable_for_the_audit_log(self) -> None:
        settings = DecisionLayerSettings(enabled=False)
        client = DecisionClient(settings)
        payload = evaluate_tool_call(
            client, settings, tool="pesquisar_web", arguments={"consulta": "celsius"}
        ).as_dict()
        assert payload["tool"] == "pesquisar_web"
        assert payload["requires_confirmation"] is False
        assert payload["risk"] == Risk.READ.value
        assert "celsius" in payload["args_summary"]


class TestEveryRealToolHasAPolicy:
    def test_no_real_tool_is_left_unclassified(self) -> None:
        """Fail-closed must not degrade into "every tool asks for approval"."""
        from ai.tools import REGISTRO_FERRAMENTAS
        from core.tool_policy import get_policy

        missing = [f.nome for f in REGISTRO_FERRAMENTAS if get_policy(f.nome) is None]
        assert missing == []
