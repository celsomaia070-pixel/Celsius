"""Tests for Phase 7: Conditional reflection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai.reflection import (
    ReflectionResult,
    _answer_contradicts_tool_result,
    _ended_by_iteration_limit,
    _task_incomplete,
    _tool_failed_and_no_retry,
    _tools_were_expected_but_none_used,
    reflect,
    should_reflect,
)


class MockPasso:
    def __init__(self, tipo: str, resultado: str | None = None, conteudo: str = ""):
        self.tipo = tipo
        self.resultado = resultado
        self.conteudo = conteudo


class TestReflectionPredicates:
    def test_tools_expected_none_used(self):
        passos = [MockPasso("resposta", conteudo="Olá!")]
        assert _tools_were_expected_but_none_used(
            "liste meus documentos", ["listar_documentos_rag"], passos
        )

    def test_tools_expected_none_used_but_tool_used(self):
        passos = [MockPasso("acao"), MockPasso("observacao", resultado="ok")]
        assert not _tools_were_expected_but_none_used(
            "liste meus documentos", ["listar_documentos_rag"], passos
        )

    def test_tools_expected_none_used_no_tools_offered(self):
        passos = [MockPasso("resposta", conteudo="Olá!")]
        assert not _tools_were_expected_but_none_used("o que é python?", [], passos)

    def test_tool_failed_no_retry(self):
        passos = [
            MockPasso("acao"),
            MockPasso(
                "observacao", resultado="Erro ao executar ler_arquivo: arquivo nao encontrado"
            ),
            MockPasso("resposta", conteudo="Não encontrei o arquivo"),
        ]
        assert _tool_failed_and_no_retry(passos)

    def test_tool_failed_but_retried(self):
        passos = [
            MockPasso("acao"),
            MockPasso(
                "observacao", resultado="Erro ao executar ler_arquivo: arquivo nao encontrado"
            ),
            MockPasso("acao"),
            MockPasso("observacao", resultado="ok"),
            MockPasso("resposta", conteudo="Aqui está o conteúdo"),
        ]
        assert not _tool_failed_and_no_retry(passos)

    def test_answer_contradicts_tool_result(self):
        passos = [
            MockPasso("acao"),
            MockPasso("observacao", resultado="Encontrados 5 documentos: A, B, C, D, E"),
        ]
        assert _answer_contradicts_tool_result("Não encontrei nenhum documento", passos)

    def test_answer_matches_tool_result(self):
        passos = [
            MockPasso("acao"),
            MockPasso("observacao", resultado="Encontrados 5 documentos"),
        ]
        assert not _answer_contradicts_tool_result("Encontrei 5 documentos", passos)

    def test_ended_by_iteration_limit(self):
        assert _ended_by_iteration_limit(10, 9)
        assert not _ended_by_iteration_limit(10, 5)

    def test_task_incomplete(self):
        task = SimpleNamespace(task={"plan": [{"step": 1}, {"step": 2}]}, output=None)
        assert _task_incomplete([], task)

    def test_task_complete(self):
        task = SimpleNamespace(task={"plan": []}, output="done")
        assert not _task_incomplete([], task)

    def test_task_no_plan(self):
        task = SimpleNamespace(task={}, output=None)
        assert not _task_incomplete([], task)


class TestShouldReflect:
    def test_triggers_on_zero_tools(self):
        passos = [MockPasso("resposta", conteudo="Olá")]
        assert should_reflect(
            "liste meus arquivos",
            "Ok",
            ["listar_documentos_rag"],
            passos,
            None,
            10,
            0,
        )

    def test_triggers_on_tool_failure(self):
        passos = [
            MockPasso("acao"),
            MockPasso("observacao", resultado="Erro ao executar X"),
            MockPasso("resposta", conteudo="Deu erro"),
        ]
        assert should_reflect(
            "qualquer coisa",
            "Deu erro",
            ["ler_arquivo"],
            passos,
            None,
            10,
            0,
        )

    def test_triggers_on_iteration_limit(self):
        passos = [MockPasso("resposta", conteudo="Ok")]
        assert should_reflect(
            "qualquer coisa",
            "Ok",
            [],
            passos,
            None,
            10,
            9,
        )

    def test_does_not_trigger_when_clean(self):
        passos = [
            MockPasso("acao"),
            MockPasso("observacao", resultado="ok"),
            MockPasso("resposta", conteudo="Aqui está o resultado"),
        ]
        assert not should_reflect(
            "liste arquivos",
            "Aqui estão: A, B",
            ["listar_documentos_rag"],
            passos,
            None,
            10,
            0,
        )


class TestReflect:
    def test_returns_needs_action_for_zero_tools(self):
        passos = [MockPasso("resposta", conteudo="Olá")]
        result = reflect(
            "liste meus documentos",
            "Olá",
            ["listar_documentos_rag"],
            passos,
            None,
            max_iteracoes=10,
            iteracao_atual=0,
        )
        assert isinstance(result, ReflectionResult)
        assert result.needs_action
        assert "ferramentas" in result.reason.lower()

    def test_returns_no_action_when_clean(self):
        passos = [
            MockPasso("acao"),
            MockPasso("observacao", resultado="ok"),
            MockPasso("resposta", conteudo="Resultado: 5 itens"),
        ]
        result = reflect(
            "quantos itens?",
            "Resultado: 5 itens",
            ["consultar_estoque"],
            passos,
            None,
            max_iteracoes=10,
            iteracao_atual=0,
        )
        assert not result.needs_action


class TestSettings:
    def test_reflection_settings_exist(self):
        from core.settings import get_settings

        s = get_settings().agent
        assert hasattr(s, "reflection_enabled")
        assert hasattr(s, "reflection_max_turns")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
