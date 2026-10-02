"""Routing contracts shared by desktop, web and WhatsApp."""

import pytest

from core.message_intent import classify_intent, normalize_text
from core.quick_response import quick_response


@pytest.fixture
def actual_agents(monkeypatch):
    # The suite globally stubs ai.agents; exercise its real cheap classifier.
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "intent_agents_test", Path(__file__).parents[1] / "ai/agents.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "text",
    [
        "quem é voce?",
        "quem é voce e o que voce pode realizar?",
        "QUEM É VOCÊ?!",
        "  TAREFA : Quem e voce? ",
        "olá me diga as suas capacidades",
        "Olá, quais são suas capacidades?",
        "TAREFA: OLÁ! ME DIGA AS SUAS CAPACIDADES...",
        "Oi, o que você sabe fazer?",
        "TAREFA: Boa tarde",
        "Olá Celsius, tudo bem?",
    ],
)
def test_meta_requests_are_cheap_even_from_old_clients(text):
    assert classify_intent(text).kind == "conversation"
    assert quick_response(text)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Olá, consulte meu estoque", "tools"),
        ("olá consulte meu estoque!", "tools"),
        ("Boa tarde, quais documentos eu tenho?", "tools"),
        ("Pesquise a previsão do tempo em Marília SP", "tools"),
        ("Olá, quais são suas capacidades e consulte meu estoque", "tools"),
        ("TAREFA: Olá, consulte meu estoque", "task"),
        ("Gere um relatório de estoque", "task"),
        ("Olá, preencha meu documento Word", "task"),
        ("Quem é você e gere um relatório", "task"),
        ("Explique energia solar", "general"),
        ("O que é um estoque?", "general"),
        ("Olá, como funciona um PDF?", "general"),
        ("TAREFA: Explique energia solar", "task"),
        ("AUTORIZAR ABC123", "control"),
        ("CANCELAR TAREFA abcdef123456", "control"),
        ("RETOMAR abcdef123456", "control"),
    ],
)
def test_complete_request_decides_routing(text, kind):
    assert classify_intent(text).kind == kind
    assert quick_response(text) is None


def test_attachment_never_disappears_behind_a_greeting():
    assert classify_intent("Olá", has_attachment=True).operational
    assert quick_response("Olá", has_attachment=True) is None


def test_normalization_is_accent_and_punctuation_independent():
    assert normalize_text("Olá! Previsão: MARÍLIA/SP?") == "ola previsao marilia sp"


def test_context_is_only_requested_when_relevant():
    general = classify_intent("Explique energia solar")
    assert not general.needs_memory and not general.needs_rag
    local = classify_intent("Resuma os documentos indexados do meu aluno")
    assert not local.needs_memory and local.needs_rag
    assert not classify_intent("Resuma este documento", has_attachment=True).needs_rag
    assert not classify_intent("Consulte meu estoque").needs_memory
    assert classify_intent("Quem sou eu?").needs_memory


@pytest.mark.parametrize(
    "text",
    [
        "O que já está armazenado aqui?",
        "Me mostra o que tem guardado no sistema",
        "Tem alguma coisa arquivada que eu possa ver?",
        "Quando é o meu próximo compromisso?",
        "Me ajuda a montar um código que resolva X",
        "Quero ver o panorama das vendas",
        "O que você sabe sobre o que já conversamos?",
        "Preciso do material guardado no computador",
    ],
)
def test_local_paraphrases_reach_tools_instead_of_general_chat(text):
    assert classify_intent(text).operational


def test_clear_inventory_lookup_does_not_need_semantic_retrieval(monkeypatch):
    import ai.react as react

    monkeypatch.setattr(
        react.tool_retrieval, "score_tools", lambda *a: pytest.fail("unnecessary embedding")
    )
    assert "listar_estoque" in {
        tool.nome for tool in react._filtrar_ferramentas("Olá, consulte meu estoque")
    }


def test_filters_share_compound_request_decision(monkeypatch):
    import ai.tool_retrieval as retrieval
    from core.agent_modes import is_conversational_greeting

    monkeypatch.setattr(retrieval, "get_embedding_model", lambda: pytest.fail("embedding"))
    for text in ("quem é voce?", "olá me diga as suas capacidades", "Explique energia solar"):
        assert retrieval.score_tools(text) == {}
    for text in ("Olá, consulte meu estoque", "TAREFA: Boa tarde, gere um relatório"):
        assert not is_conversational_greeting(text)
        assert not retrieval._is_conversational(text)


def test_general_selection_and_classification_never_load_embeddings(monkeypatch, actual_agents):
    agents = actual_agents
    import ai.react as react
    import core.agent_modes as modes

    monkeypatch.setattr(agents, "_compute_agent_embeddings", lambda: pytest.fail("semantic"))
    monkeypatch.setattr(modes, "classify_mode", lambda *a: pytest.fail("semantic"))
    monkeypatch.setattr(react.tool_retrieval, "score_tools", lambda *a: pytest.fail("retrieval"))
    assert react._filtrar_ferramentas("O que é um estoque?") == []
    assert agents.classificar_tarefa("Explique energia solar") is None
    assert modes.resolve_mode("quem é voce?") == "assistente"


def test_known_mode_does_not_load_another_semantic_specialist(monkeypatch, actual_agents):
    agents = actual_agents

    monkeypatch.setattr(agents, "_compute_agent_embeddings", lambda: pytest.fail("semantic"))
    assert agents.classificar_tarefa("Consulte meu estoque", semantic=False) is None
