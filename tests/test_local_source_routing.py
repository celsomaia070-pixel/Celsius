"""An explicit local source must not be replaced by an internet search."""

import pytest

from core.message_intent import classify_intent, is_local_memory_read

QUESTION = "o celsius tem alguma relação com o tecunimar, procure nas memorias"


@pytest.mark.parametrize(
    "question",
    [
        QUESTION,
        "TAREFA: " + QUESTION,
        "Olá, pesquise sobre TecUnimar nas memórias!",
        "Procure nas minhas memórias a relação com TecUnimar",
        "Pesquise as notícias guardadas nas memórias",
        "Procure meu estoque",
        "Busque nos documentos a data da reunião",
    ],
)
def test_local_queries_do_not_use_generic_web_shortcut(monkeypatch, question):
    from core import commands, web_research

    def forbidden(*args, **kwargs):
        pytest.fail("local query sent to internet or browser")

    monkeypatch.setattr(commands, "pesquisar_web", forbidden)
    monkeypatch.setattr(commands.webbrowser, "open", forbidden)
    assert commands.executar_comando(question) is None
    assert web_research.is_web_lookup(question) is False


@pytest.mark.parametrize("question", [QUESTION, "Olá, pesquise sobre TecUnimar nas memórias!"])
def test_memory_read_uses_only_memory_tool_without_semantic_classification(monkeypatch, question):
    import ai.react as react
    import core.agent_modes as modes

    monkeypatch.setattr(react.tool_retrieval, "score_tools", lambda *a: pytest.fail("encoder"))
    monkeypatch.setattr(modes, "classify_mode", lambda *a: pytest.fail("mode encoder"))
    assert classify_intent(question).needs_memory
    assert is_local_memory_read(question)
    assert {f.nome for f in react._filtrar_ferramentas(question)} == {"buscar_memoria"}
    assert modes.resolve_mode(question, requested="assistente") == "assistente"
    assert modes.resolve_mode(question, requested="documentos") == "documentos"


@pytest.mark.parametrize(
    "question",
    [
        "Pesquise na internet sobre memória humana",
        "Procure nas memórias e consulte o estoque",
        "Procure nas memórias e envie para meu contato",
        "Compare minhas memórias com notícias da internet",
    ],
)
def test_compound_requests_keep_normal_agent_flow(question):
    assert not is_local_memory_read(question)


def test_real_web_lookup_remains_available(monkeypatch):
    from core import commands, web_research

    queries = []
    monkeypatch.setattr(commands, "pesquisar_web", lambda q: queries.append(q) or "sources")
    assert commands.executar_comando("Procure na internet TecUnimar") == "sources"
    assert queries == ["tecunimar"]
    assert web_research.is_web_lookup("Pesquise na internet sobre memória humana")


def test_engine_preserves_memory_context_instead_of_returning_web_results(monkeypatch):
    import ai.engine as engine

    captured = []
    monkeypatch.setattr(engine, "executar_comando", lambda *a: pytest.fail("legacy shortcut"))

    def respond(prompt, **kwargs):
        captured.append(prompt)
        assert prompt["memorias_relevantes"] == ["Fato local de teste sobre TecUnimar"]
        return "Resposta baseada na memória local", []

    monkeypatch.setattr(engine, "loop_react", respond)
    result = engine.gerar_resposta(
        {"pergunta": QUESTION, "memorias_relevantes": ["Fato local de teste sobre TecUnimar"]}
    )
    assert result == "Resposta baseada na memória local"
    assert len(captured) == 1


def test_memory_topic_retrieval_does_not_load_embeddings(tmp_path, monkeypatch):
    from core.memory import MemoryService
    from core.settings import Settings
    from core.sqlite_store import connect

    service = MemoryService(Settings(base_dir=tmp_path, memorias_file=tmp_path / "memorias.json"))
    with connect(service._db_path) as conn:
        conn.execute(
            "INSERT INTO memories (texto, data, origem, conversation_id) VALUES (?, ?, ?, ?)",
            ("Registro local de teste sobre TecUnimar", "", "usuario", ""),
        )
    service._load()
    monkeypatch.setattr(
        MemoryService, "_model_instance", property(lambda _self: pytest.fail("encoder"))
    )
    assert service.search(QUESTION) == ["Registro local de teste sobre TecUnimar"]


@pytest.mark.parametrize("memories", [["Fato local de teste sobre TecUnimar"], []])
def test_real_react_prompt_scopes_memory_without_web_or_encoder(tmp_path, monkeypatch, memories):
    from types import SimpleNamespace

    import ai.agents as agents
    import ai.engine as engine
    import ai.react as react
    from core.settings import Settings

    settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
    for module in (engine, react):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    for module, name in (
        (react.tool_retrieval, "score_tools"),
        (agents, "_compute_agent_embeddings"),
        (engine, "executar_comando"),
        (react, "executar_ferramenta"),
    ):
        monkeypatch.setattr(module, name, lambda *a, **k: pytest.fail("unexpected resource"))
    requests = []

    class Model:
        def create_chat_completion(self, **kwargs):
            requests.append(kwargs)
            all_text = "\n".join(str(m.get("content", "")) for m in kwargs["messages"])
            assert "Nao use resultados web" in all_text
            assert "nao invente uma relacao" in all_text
            assert all("FONTE_WEB" not in str(m.get("content", "")) for m in kwargs["messages"])
            assert {t["function"]["name"] for t in kwargs.get("tools", [])} <= {"buscar_memoria"}
            if memories:
                assert memories[0] in all_text
            yield {"choices": [{"delta": {"content": "Resposta proporcional ao registro local."}}]}

    manager = SimpleNamespace(
        route_and_invoke=lambda *a, **k: (settings.llm_model, Model()),
        get_last_decision=lambda: None,
        get_current_complexity=lambda: "simple",
    )
    monkeypatch.setattr(react, "get_multi_model_manager", lambda: manager)
    engine.gerar_resposta(
        {
            "pergunta": "Analise a relação. " + QUESTION,
            "memorias_relevantes": memories,
            "memorias_consultadas": True,
            "agent_mode": "assistente",
        }
    )
    assert len(requests) == 1


@pytest.mark.parametrize("memories", [["Registro exato de teste: incubadora do TecUnimar"], []])
def test_simple_memory_lookup_cannot_invent_affiliations_or_use_model(monkeypatch, memories):
    import ai.engine as engine
    import ai.react as react

    monkeypatch.setattr(react, "get_multi_model_manager", lambda: pytest.fail("model"))
    monkeypatch.setattr(react.tool_retrieval, "score_tools", lambda *a: pytest.fail("encoder"))
    response = engine.gerar_resposta(
        {
            "pergunta": QUESTION,
            "memorias_relevantes": memories,
            "memorias_consultadas": True,
            "agent_mode": "assistente",
        }
    )
    if memories:
        assert response == "Nas suas memórias, encontrei estes registros:\n\n> " + memories[0]
    else:
        assert "Não encontrei registro relevante" in response
    assert "IFMA" not in response
