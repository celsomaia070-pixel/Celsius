"""Browser openings must preserve the search and approval without using AI."""

import time
from urllib.parse import parse_qs, urlparse

import pytest

from core.direct_actions import youtube_open_arguments


@pytest.mark.parametrize(
    "text,term",
    [
        ("TAREFA: Abra o YouTube em Tim Maia", "Tim Maia"),
        ("Abra Tim Maia no YouTube", "Tim Maia"),
        ("Olá, abra o YouTube e pesquise por João Gilberto!", "João Gilberto"),
        ("Por favor, pode abrir You Tube com AC/DC?", "AC/DC"),
        ("Abrir YouTube", ""),
    ],
)
def test_unambiguous_youtube_open_preserves_query(text, term):
    args = youtube_open_arguments(text)
    parsed = urlparse(args["url"])
    assert parsed.hostname == "www.youtube.com"
    assert parse_qs(parsed.query).get("search_query", [""])[0] == term


@pytest.mark.parametrize(
    "text",
    [
        "Explique como abrir o YouTube",
        "Abra o YouTube em Tim Maia e baixe um vídeo",
        "Abra o YouTube em Tim Maia e faça um relatório",
        "Abra YouTube; envie uma mensagem",
        "Analise as músicas de Tim Maia no YouTube",
        "Abra o Google em Tim Maia",
    ],
)
def test_complex_or_unrelated_request_keeps_normal_flow(text):
    assert youtube_open_arguments(text) is None


@pytest.fixture
def browser_chat(tmp_path, monkeypatch):
    import ai.engine as engine
    import ai.react as react
    import ai.tools as tools
    import core.file_security as security
    from core.agent_tasks import AgentTaskStore
    from core.chat_service import ChatCoordinator
    from core.conversations import ConversationManager
    from core.settings import Settings
    from core.web_api.events import EventHub

    settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
    monkeypatch.setattr(security, "_allowed_roots", [tmp_path])
    for module in (engine, react, tools):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(react.tool_retrieval, "score_tools", lambda *a: pytest.fail("encoder"))
    monkeypatch.setattr(react, "get_multi_model_manager", lambda: pytest.fail("model"))
    coordinator = ChatCoordinator(
        settings=settings,
        event_hub=EventHub(),
        conversation_manager=ConversationManager(tmp_path / "conversations"),
        ensure_model_ready=lambda _: pytest.fail("model loaded"),
    )
    try:
        yield coordinator, AgentTaskStore(settings.data_dir / "agent_tasks.db")
    finally:
        coordinator.shutdown()


def send(coordinator, text, conversation_id="", **kwargs):
    job = coordinator.submit(
        message=text, conversation_id=conversation_id, source="whatsapp", **kwargs
    )
    deadline = time.monotonic() + 5
    while job["status"] not in {"completed", "failed", "cancelled"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
        job = coordinator.get_job(job["id"])
    assert job["status"] == "completed", job.get("error")
    assert job["timings"]["model_state"] == "not_used"
    assert "tool_selection" not in job["timings"]["phases_ms"]
    return job


@pytest.mark.parametrize("work_agents", [[], ["pesquisador", "documentos"]])
def test_youtube_task_is_fast_before_and_after_approval(browser_chat, monkeypatch, work_agents):
    import webbrowser

    coordinator, store = browser_chat
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    initial = send(coordinator, "TAREFA: Abra o YouTube em Tim Maia", work_agents=work_agents)
    task = store.list(initial["conversation_id"])[0]
    assert task["status"] == "waiting_confirmation"
    assert opened == []
    assert len(task["steps"]) == 1
    code = task["steps"][0]["approval_code"]
    assert "AUTORIZAR " + code in initial["response"]
    approved = send(coordinator, "AUTORIZAR " + code, initial["conversation_id"])
    assert opened == ["https://www.youtube.com/results?search_query=Tim+Maia"]
    assert "Abertura solicitada" in approved["response"]
    completed = store.get(task["id"], initial["conversation_id"])
    assert completed["status"] == "completed"
    assert len(completed["steps"]) == 1
    send(coordinator, "AUTORIZAR " + code, initial["conversation_id"])
    assert len(opened) == 1


def test_browser_refusal_is_reported_as_task_failure(browser_chat, monkeypatch):
    import webbrowser

    coordinator, store = browser_chat
    monkeypatch.setattr(webbrowser, "open", lambda url: False)
    initial = send(coordinator, "TAREFA: Abra o YouTube em Tim Maia")
    task = store.list(initial["conversation_id"])[0]
    response = send(
        coordinator, "AUTORIZAR " + task["steps"][0]["approval_code"], initial["conversation_id"]
    )
    assert "não aceitou" in response["response"]
    failed = store.get(task["id"], initial["conversation_id"])
    assert failed["status"] == "failed"
    assert failed["steps"][0]["status"] == "failed"


def test_non_task_browser_request_does_not_use_legacy_homepage_shortcut(browser_chat, monkeypatch):
    import webbrowser

    coordinator, _ = browser_chat
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    initial = send(coordinator, "Abra o YouTube em Tim Maia")
    assert "AUTORIZAR" in initial["response"]
    assert "search_query=Tim+Maia" in initial["response"]
    assert opened == []


def test_old_pending_task_resumes_once_without_second_approval(browser_chat, monkeypatch):
    import webbrowser

    coordinator, store = browser_chat
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url) or True)
    initial = send(coordinator, "TAREFA: Abra o YouTube em Tim Maia")
    task = store.list(initial["conversation_id"])[0]
    step = task["steps"][0]
    step["arguments"] = {"url": "youtube Tim Maia"}
    code = step["approval_code"]
    store.save(task)
    approved = send(coordinator, "AUTORIZAR " + code, initial["conversation_id"])
    assert "Abertura solicitada" in approved["response"]
    assert len(opened) == 1
    assert parse_qs(urlparse(opened[0]).query)["search_query"][0].casefold() == "tim maia"
    assert len(store.get(task["id"], initial["conversation_id"])["steps"]) == 1


def test_approval_from_other_conversation_cannot_open_browser(browser_chat, monkeypatch):
    import webbrowser

    coordinator, store = browser_chat
    monkeypatch.setattr(webbrowser, "open", lambda *a: pytest.fail("unauthorized browser"))
    initial = send(coordinator, "TAREFA: Abra o YouTube em Tim Maia")
    task = store.list(initial["conversation_id"])[0]
    send(coordinator, "AUTORIZAR " + task["steps"][0]["approval_code"])
    assert store.get(task["id"], initial["conversation_id"])["status"] == "waiting_confirmation"


def test_rejecting_open_does_not_execute_or_resume(browser_chat, monkeypatch):
    import webbrowser

    coordinator, store = browser_chat
    monkeypatch.setattr(webbrowser, "open", lambda *a: pytest.fail("cancelled browser"))
    initial = send(coordinator, "TAREFA: Abra o YouTube em Tim Maia")
    task = store.list(initial["conversation_id"])[0]
    send(coordinator, "CANCELAR " + task["steps"][0]["approval_code"], initial["conversation_id"])
    send(coordinator, "RETOMAR " + task["id"], initial["conversation_id"])
    assert store.get(task["id"], initial["conversation_id"])["status"] == "cancelled"


def test_cancel_after_browser_effect_saves_progress_without_replaying(browser_chat, monkeypatch):
    import threading
    import webbrowser

    import ai.engine as engine

    coordinator, store = browser_chat
    opened = []
    cancelled = threading.Event()

    def open_browser(url):
        opened.append(url)
        cancelled.set()
        return True

    monkeypatch.setattr(webbrowser, "open", open_browser)
    initial = send(coordinator, "TAREFA: Abra o YouTube em Tim Maia")
    task = store.list(initial["conversation_id"])[0]
    response = engine.gerar_resposta(
        {
            "pergunta": "AUTORIZAR " + task["steps"][0]["approval_code"],
            "approval_scope": initial["conversation_id"],
        },
        should_cancel=cancelled.is_set,
    )
    assert "cancelled" in response
    assert len(opened) == 1
    saved = store.get(task["id"], initial["conversation_id"])
    assert saved["status"] == "cancelled"
    assert saved["steps"][0]["status"] == "succeeded"
