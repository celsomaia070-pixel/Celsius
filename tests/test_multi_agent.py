from pathlib import Path

from ai.multi_agent import AgentRunStore, run_multi_agent_work
from core.tool_approval import APPROVAL_REQUIRED_PREFIX


def test_work_mode_gives_each_agent_an_independent_context(tmp_path: Path):
    calls = []

    def responder(prompt, **_kwargs):
        calls.append(prompt)
        if prompt.get("disable_tools"):
            return "resposta consolidada"
        return f"contribuicao de {prompt['agent_mode']}"

    result = run_multi_agent_work(
        {
            "pergunta": "pesquise e produza um relatorio",
            "approval_scope": "conversation-1",
            "historico": [{"role": "user", "content": "nao compartilhar"}],
            "work_agents": ["pesquisador", "documentos"],
        },
        responder,
        data_dir=tmp_path,
    )

    assert result == "resposta consolidada"
    assert [call["agent_mode"] for call in calls] == [
        "pesquisador",
        "documentos",
        "assistente",
    ]
    assert calls[0]["historico"] == []
    assert calls[1]["historico"] == []
    assert calls[2]["disable_tools"] is True
    assert (tmp_path / "agent_runs.db").is_file()


def test_agent_run_store_persists_a_private_checkpoint(tmp_path: Path):
    store = AgentRunStore(tmp_path)
    checkpoint = {
        "id": "run-1",
        "scope": "conversation-1",
        "objective": "objetivo",
        "status": "running",
        "created": 1.0,
    }
    store.save(checkpoint)
    assert store.path.is_file()
    assert store.get("run-1", "conversation-1")["objective"] == "objetivo"
    assert store.list("conversation-1")[0]["id"] == "run-1"


def test_multi_agent_run_resumes_after_tool_approval(tmp_path: Path):
    calls = []

    def responder(prompt, **_kwargs):
        calls.append((prompt["pergunta"], prompt.get("agent_mode")))
        if prompt["pergunta"] == "AUTORIZAR ABCD1234":
            return "acao autorizada e executada"
        if prompt.get("disable_tools"):
            return "consolidado depois da aprovacao"
        if prompt["agent_mode"] == "documentos":
            return f"{APPROVAL_REQUIRED_PREFIX}\nAUTORIZAR ABCD1234"
        return "contribuicao restante"

    initial = {
        "pergunta": "crie e revise um documento",
        "approval_scope": "conversation-1",
        "work_agents": ["documentos", "pesquisador"],
    }
    waiting = run_multi_agent_work(initial, responder, data_dir=tmp_path)
    assert "AUTORIZAR ABCD1234" in waiting

    resumed = run_multi_agent_work(
        {**initial, "pergunta": "AUTORIZAR ABCD1234"}, responder, data_dir=tmp_path
    )
    assert resumed == "consolidado depois da aprovacao"
    assert calls.count(("crie e revise um documento", "documentos")) == 0
    completed = AgentRunStore(tmp_path).list("conversation-1")[0]
    assert completed["status"] == "completed"
    assert [item["id"] for item in completed["agents"]] == ["documentos", "pesquisador"]
