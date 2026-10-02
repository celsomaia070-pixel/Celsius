from pathlib import Path

from core.agent_artifacts import task_requests_artifact, verify_task, workspace_for
from core.agent_schedule import AgentScheduleStore
from core.agent_tasks import AgentTaskStore
from ai.task_runtime import TaskSession


def test_workspace_isolated_and_verifies_json(tmp_path):
    workspace = workspace_for(tmp_path, "a1b2c3")
    output = workspace / "answer.json"
    output.write_text('{"ok": true}', encoding="utf-8")
    task = {"id": "a1b2c3", "steps": []}

    report = verify_task(task, tmp_path)

    assert report["passed"] is True
    assert report["artifact_count"] == 1
    assert report["artifacts"][0]["sha256"]
    assert report["artifacts"][0]["valid_json"] is True


def test_artifact_objectives_are_identified_without_treating_summaries_as_files():
    assert task_requests_artifact({"objective": "Gere um relatorio PEI em PDF"})
    assert task_requests_artifact({"objective": "Preencha este formulario"})
    assert not task_requests_artifact({"objective": "Resuma o relatorio PEI"})


def test_task_cannot_complete_a_document_request_without_a_real_artifact(tmp_path):
    store = AgentTaskStore(tmp_path / "agent_tasks.db")
    task = store.create("abc123def456", {"pergunta": "Gere um relatorio PEI em PDF para o aluno."})

    completed = TaskSession(store, task).finish("Relatorio pronto em um caminho ficticio.")
    saved = store.get(task["id"], task["scope"])

    assert completed is False
    assert saved["status"] == "failed"
    assert "Nenhum arquivo" in saved["error"]


def test_a_generic_report_does_not_complete_a_template_fill_task(tmp_path):
    from docx import Document

    store = AgentTaskStore(tmp_path / "agent_tasks.db")
    task = store.create("abc123def456", {"pergunta": "Preencha o documento anexado"})
    workspace = Path(task["workspace"])
    document = Document()
    document.add_paragraph("Um relatorio novo que nao usa o modelo")
    document.save(workspace / "outro_relatorio.docx")
    assert TaskSession(store, task).finish("Pronto") is False
    saved = store.get(task["id"], task["scope"])
    assert saved["status"] == "failed"
    assert "nao substitui" in saved["error"]


def test_schedule_is_durable_and_does_not_repeat_due_item(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("core.agent_schedule.time.time", lambda: now[0])
    store = AgentScheduleStore(tmp_path)
    item = store.create(
        scope="abc123def456", objective="Verifique estoque", mode="executor", every_seconds=60
    )
    now[0] += 61

    assert [due["id"] for due in store.due()] == [item["id"]]
    assert store.due() == []
    assert AgentScheduleStore(tmp_path).list(item["scope"])[0]["next_run"] > now[0]


def test_schedule_dispatch_failure_is_retried_and_success_is_recorded(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("core.agent_schedule.time.time", lambda: now[0])
    store = AgentScheduleStore(tmp_path)
    item = store.create(
        scope="abc123def456", objective="Verifique estoque", mode="executor", every_seconds=60
    )
    now[0] += 61
    assert store.due()

    store.defer(item["id"], "fila ocupada", retry_seconds=30)
    scheduled = store.list(item["scope"])[0]
    assert scheduled["last_error"] == "fila ocupada"
    assert scheduled["next_run"] == now[0] + 30
    now[0] += 31
    assert store.due()

    store.record_dispatch(item["id"], "job-123")
    scheduled = store.list(item["scope"])[0]
    assert scheduled["last_error"] == ""
    assert scheduled["last_job_id"] == "job-123"
    assert scheduled["run_count"] == 1


def test_mode_preference_is_durable(tmp_path):
    store = AgentTaskStore(tmp_path / "agent_tasks.db")
    assert store.set_mode("abc123def456", "pesquisador") == "pesquisador"
    assert AgentTaskStore(store.path).get_mode("abc123def456") == "pesquisador"
