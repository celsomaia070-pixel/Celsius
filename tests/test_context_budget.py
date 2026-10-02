"""Tests for Phase 5: WorkingMemory and context budget improvements."""

from __future__ import annotations

from ai.context_budget import ContextBudget, WorkingMemory, _simple_summarize, estimate_tokens


class TestWorkingMemory:
    def test_empty_memory_renders_none(self):
        wm = WorkingMemory()
        assert wm.para_system_prompt() is None

    def test_fatos_confirmados(self):
        wm = WorkingMemory()
        wm.adicionar_fato("Cliente João tem 35 anos")
        wm.adicionar_fato("Produto X custa R$ 100")
        prompt = wm.para_system_prompt()
        assert "Fatos confirmados" in prompt
        assert "Cliente João tem 35 anos" in prompt
        assert "Produto X custa R$ 100" in prompt

    def test_tarefas_pendentes(self):
        wm = WorkingMemory()
        wm.adicionar_tarefa("Ler contrato")
        wm.adicionar_tarefa("Resumir pontos principais")
        prompt = wm.para_system_prompt()
        assert "Tarefas pendentes" in prompt
        assert "Ler contrato" in prompt

    def test_resultados_recentes(self):
        wm = WorkingMemory()
        wm.adicionar_resultado("consultar_estoque -> 50 unidades")
        wm.adicionar_resultado("ler_arquivo -> conteúdo do PDF")
        prompt = wm.para_system_prompt()
        assert "Resultados recentes" in prompt
        assert "consultar_estoque -> 50 unidades" in prompt

    def test_deduplication(self):
        wm = WorkingMemory()
        wm.adicionar_fato("Fato A")
        wm.adicionar_fato("Fato A")  # duplicate
        wm.adicionar_fato("Fato B")
        assert len(wm.fatos_confirmados) == 2

    def test_max_items_limit(self):
        wm = WorkingMemory()
        for i in range(15):
            wm.adicionar_fato(f"Fato {i}")
        assert len(wm.fatos_confirmados) == WorkingMemory.MAX_ITENS

    def test_truncation(self):
        wm = WorkingMemory()
        wm.adicionar_fato("X" * 500)
        assert len(wm.fatos_confirmados[0]) <= WorkingMemory.MAX_CHARS_ITEM

    def test_limpar_concluidas(self):
        wm = WorkingMemory()
        wm.adicionar_tarefa("Tarefa 1")
        wm.adicionar_tarefa("Tarefa 2")
        wm.limpar_concluidas(["Tarefa 1"])
        assert "Tarefa 1" not in wm.tarefas_pendentes
        assert "Tarefa 2" in wm.tarefas_pendentes

    def test_estimate_tokens(self):
        wm = WorkingMemory()
        # Empty WM has framing tokens
        assert wm.estimate_tokens() == 4
        wm.adicionar_fato("Fato teste")
        tokens = wm.estimate_tokens()
        assert tokens > 4


class TestContextBudgetWithWorkingMemory:
    def test_analyze_messages_includes_wm(self):
        budget = ContextBudget(num_ctx=4096)
        wm = WorkingMemory()
        wm.adicionar_fato("Fato importante")
        wm.adicionar_tarefa("Tarefa pendente")

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Olá"},
            {"role": "assistant", "content": "Oi!"},
        ]
        analysis = budget.analyze_messages(messages, wm)

        assert "working_memory_tokens" in analysis
        assert analysis["working_memory_tokens"] > 0
        assert analysis["total_used"] == (
            analysis["system_tokens"]
            + analysis["history_tokens"]
            + analysis["document_tokens"]
            + analysis["tool_tokens"]
            + analysis["working_memory_tokens"]
        )

    def test_wm_budget_warning(self):
        budget = ContextBudget(num_ctx=1000)  # tiny context
        wm = WorkingMemory()
        # Fill WM to exceed its budget (15% of available ~ 127 tokens)
        # Each fact ~ 200 chars = ~57 tokens. Need ~3 facts to exceed.
        for _ in range(10):
            wm.adicionar_fato("X" * 500)

        messages = [{"role": "system", "content": "Sys"}]
        analysis = budget.analyze_messages(messages, wm)
        assert any("Working memory" in w for w in analysis["warnings"])

    def test_trim_history_relevance_over_fifo(self):
        budget = ContextBudget(num_ctx=2048)
        # Create messages where oldest is highly relevant (tool result)
        messages = [
            {"role": "system", "content": "System"},
            {"role": "tool", "content": "Resultado importante da consulta de estoque: 100 unidades"},
            {"role": "user", "content": "Qual o preço?"},
            {"role": "assistant", "content": "O preço é X"},
            {"role": "user", "content": "E a cor?"},
            {"role": "assistant", "content": "A cor é azul"},
            {"role": "user", "content": "Tem em estoque?"},
            {"role": "assistant", "content": "Sim, tem 100"},
        ]
        # Set a tight history budget
        budget.history_max = 100

        # Trim with query terms matching the tool result
        query_terms = {"estoque", "consulta", "unidades"}
        trimmed = budget.trim_history(messages, query_terms=query_terms)

        # Tool result should be kept (high relevance), oldest user/assistant may be dropped
        tool_kept = any(m.get("role") == "tool" for m in trimmed)
        assert tool_kept

    def test_summarize_if_needed_trigger_at_70_percent(self):
        budget = ContextBudget(num_ctx=2048)
        wm = WorkingMemory()
        # Create enough messages to trigger 70%
        messages = [{"role": "system", "content": "Sys"}]
        for i in range(20):
            messages.append({"role": "user", "content": f"Msg {i} " * 50})
            messages.append({"role": "assistant", "content": f"Resp {i} " * 50})

        # Should trigger summarization (no LLM fn, so uses local fallback)
        summarized = budget.summarize_if_needed(messages, working_memory=wm)
        # Should have system + summary + recent messages
        assert len(summarized) < len(messages)
        # Summary message should exist
        has_summary = any("Resumo da conversa anterior" in m.get("content", "") for m in summarized)
        assert has_summary

    def test_inject_working_memory(self):
        budget = ContextBudget(num_ctx=4096)
        wm = WorkingMemory()
        wm.adicionar_fato("Fato injetado")

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Oi"},
        ]
        injected = budget.inject_working_memory(messages, wm)
        # Should have system + WM + user
        assert len(injected) == 3
        assert injected[1]["role"] == "system"
        assert "Memória de trabalho" in injected[1]["content"]
        assert "Fato injetado" in injected[1]["content"]

    def test_inject_empty_wm_noop(self):
        budget = ContextBudget(num_ctx=4096)
        wm = WorkingMemory()
        messages = [{"role": "system", "content": "System"}, {"role": "user", "content": "Oi"}]
        injected = budget.inject_working_memory(messages, wm)
        assert injected == messages


class TestSimpleSummarize:
    def test_short_text_unchanged(self):
        assert _simple_summarize("Curto.") == "Curto."

    def test_long_text_summarized(self):
        text = ". ".join([f"Sentença {i}" for i in range(10)]) + "."
        summary = _simple_summarize(text)
        assert len(summary) < len(text)
        assert "Sentença 0" in summary
        assert "Sentença 9" in summary


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_roughly_correct(self):
        # ~3.5 chars per token
        assert estimate_tokens("A" * 350) == 100
        assert estimate_tokens("A" * 700) == 200


class TestBudgetStats:
    def test_includes_working_memory_max(self):
        budget = ContextBudget(num_ctx=4096)
        stats = budget.get_stats()
        assert "working_memory_max" in stats
        assert stats["working_memory_max"] > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
