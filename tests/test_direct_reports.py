"""Real local report generation must bypass model/embeddings and verify its PDF."""

import time

import pytest

from core.direct_actions import inventory_report_arguments


def test_direct_action_preserves_selected_work_agent_allowlist():
    from core.direct_actions import direct_tool_allowed

    assert not direct_tool_allowed("gerar_relatorio_local", "estoque", ["pesquisador"])
    assert not direct_tool_allowed("pesquisar_noticias", "pesquisador", ["estoque"])
    assert direct_tool_allowed("gerar_relatorio_local", "estoque", ["estoque"])


@pytest.mark.parametrize(
    "text",
    [
        "Gere uma relatório do meu estoque",
        "TAREFA: gere um relatório do estoque",
        "Por favor, pode gerar um relatório completo do meu estoque em PDF?",
        "Olá, crie um relatório do inventário em Word",
    ],
)
def test_simple_report_plan(text):
    assert inventory_report_arguments(text)["fonte"] == "Estoque"


@pytest.mark.parametrize(
    "text",
    [
        "Gere um relatório de estoque e envie para João",
        "Gere um relatório de entradas no estoque do mês passado",
        "Gere um relatório apenas dos itens críticos do estoque",
        "Gere um relatório PEI do aluno",
        "Explique como gerar um relatório do estoque",
    ],
)
def test_complex_or_different_work_is_not_replaced_by_simple_report(text):
    assert inventory_report_arguments(text) is None


@pytest.mark.parametrize("work_agents", [[], ["estoque"], ["executor", "documentos"]])
def test_stock_report_task_has_real_attachment_verified_success_and_no_model(
    tmp_path, monkeypatch, work_agents
):
    import ai.engine as engine
    import ai.react as react
    import ai.tool_retrieval as retrieval
    import ai.tools as tools
    import core.file_security as security
    import core.operations as operations
    import core.settings as config
    import core.workflows as workflows
    from core.agent_tasks import AgentTaskStore
    from core.business_records import BusinessRecordService
    from core.chat_service import ChatCoordinator
    from core.inventory import InventoryService
    from core.operations import BusinessOperationsService
    from core.settings import Settings
    from core.web_api.events import EventHub

    settings = Settings(base_dir=tmp_path, data_dir=tmp_path / "data")
    settings.features.memory = False
    settings.decision.enabled = False
    monkeypatch.setattr(security, "_allowed_roots", [tmp_path])
    for module in (engine, react, tools, config):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    inventory = InventoryService(settings=settings, data_file=tmp_path / "inventory.json")
    inventory.adicionar_item("Filtro", "Peças", 2, 5, 20)
    inventory.adicionar_item("Parafuso", "Peças", 25, 5, 20)
    records = BusinessRecordService(settings=settings, data_file=tmp_path / "records.json")
    ops = BusinessOperationsService(
        settings=settings, inventory_service=inventory, record_service=records
    )
    workflow = workflows.BusinessWorkflowService(
        settings=settings, record_service=records, operations_service=ops
    )
    monkeypatch.setattr(workflows, "get_workflow_service", lambda: workflow)
    monkeypatch.setattr(operations, "get_operations_service", lambda: ops)
    monkeypatch.setattr(retrieval, "score_tools", lambda *a, **k: pytest.fail("embedding loaded"))
    monkeypatch.setattr(react, "get_multi_model_manager", lambda: pytest.fail("model routed"))
    coordinator = ChatCoordinator(
        settings=settings,
        event_hub=EventHub(),
        ensure_model_ready=lambda _: pytest.fail("model loaded"),
    )
    try:
        job = coordinator.submit(
            message="TAREFA: Gere uma relatório do meu estoque",
            source="whatsapp",
            work_agents=work_agents,
        )
        deadline = time.monotonic() + 10
        while job["status"] not in {"completed", "failed", "cancelled"}:
            assert time.monotonic() < deadline
            time.sleep(0.01)
            job = coordinator.get_job(job["id"])
        assert job["status"] == "completed", job.get("error")
        assert job["timings"]["model_state"] == "not_used"
        assert "tool_selection" not in job["timings"]["phases_ms"]
        assert "Itens cadastrados: 2" in job["response"]
        assert "Unidades registradas: 27" in job["response"]
        assert "Filtro: 2 unidades; mínimo 5" in job["response"]
        assert "|" not in job["response"] and "[contagem]" not in job["response"]
        output = coordinator.outputs.get(job["attachments"][0]["id"])
        assert output.path.read_bytes().startswith(b"%PDF")
        assert "relatorio" in output.name
        tasks = AgentTaskStore(settings.data_dir / "agent_tasks.db").list(job["conversation_id"])
        assert tasks[0]["status"] == "completed"
        assert tasks[0]["verification"]["artifact_count"] == 1
        assert len(tasks[0]["steps"]) == 1
        assert tasks[0]["steps"][0]["tool"] == "gerar_relatorio_local"
    finally:
        coordinator.shutdown()
