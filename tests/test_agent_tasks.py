"""Exercise durable task execution with a scripted LLM, never the user's data."""

import copy
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.agent_tasks import AgentTaskStore
from core.settings import Settings


def tool_reply(*names):
    return [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": i,
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps({"value": name}),
                                },
                            }
                            for i, name in enumerate(names)
                        ]
                    }
                }
            ]
        }
    ]


def answer(text="Relatorio pronto"):
    return [{"choices": [{"delta": {"content": text}}]}]


def prose_with_tool(text, *names):
    """One turn that writes prose *and* asks for tools, as a real model does."""
    return [{"choices": [{"delta": {"content": text}}]}] + tool_reply(*names)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    # Monkeypatch core.settings.get_settings BEFORE importing modules that
    # capture the get_settings reference (e.g., loop_budget via react).
    import core.settings as core_settings_module

    settings = Settings(
        base_dir=tmp_path,
        data_dir=tmp_path / "data",
        resources_dir=tmp_path / "resources",
        logs_dir=tmp_path / "logs",
    )
    settings.model.num_ctx = 16384
    settings.decision.enabled = False

    # Must be done before importing react (which imports loop_budget)
    monkeypatch.setattr(core_settings_module, "get_settings", lambda: settings)

    import ai.engine as engine
    import ai.react as react
    import ai.tools as tools
    import core.agent_modes as modes
    import core.decisions as decisions
    import core.settings as settings_module
    import core.tool_policy as policy

    for module in (engine, react, settings_module):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(decisions, "get_decision_client", lambda: SimpleNamespace(enabled=False))
    # The fixture tools are synthetic, and the policy table fails closed for
    # unknown tools, so declare them the way a real integration would.
    monkeypatch.setitem(
        policy._POLICIES, "ler_teste", policy.ToolPolicy(policy.Risk.READ, "Ferramenta de teste.")
    )
    monkeypatch.setitem(
        policy._POLICIES,
        "criar_editar_arquivo",
        policy.ToolPolicy(policy.Risk.IRREVERSIBLE, "Ferramenta de teste."),
    )
    monkeypatch.setitem(
        policy._POLICIES,
        "salvar_memoria",
        policy.ToolPolicy(policy.Risk.WRITE, "Ferramenta de teste."),
    )
    monkeypatch.setitem(
        policy._POLICIES,
        "pesquisar_web",
        policy.ToolPolicy(policy.Risk.READ, "Ferramenta de teste."),
    )
    # A mode that may write, so the durable-task tests exercise the real
    # mode-allowlist path instead of bypassing it.
    monkeypatch.setitem(
        modes.MODES_BY_ID,
        "executor",
        modes.AgentMode(
            id="executor",
            label="Executor",
            summary="Modo de teste",
            prompt="Modo de teste",
            tools=("ler_teste", "criar_editar_arquivo", "salvar_memoria"),
            can_plan=True,
        ),
    )
    monkeypatch.setattr(react, "_agenda_prompt_context", lambda: "")
    calls, requests, replies = [], [], []
    registry = {
        name: tools.Ferramenta(
            name,
            name,
            {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
            lambda: None,
        )
        for name in ("ler_teste", "criar_editar_arquivo", "salvar_memoria")
    }
    registry["pesquisar_web"] = tools.Ferramenta(
        "pesquisar_web",
        "pesquisar_web",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        lambda: None,
    )
    monkeypatch.setattr(react, "_filtrar_ferramentas", lambda *a, **k: list(registry.values()))
    monkeypatch.setattr(tools, "obter_ferramenta", registry.get)

    def execute(name, arguments, **kwargs):
        calls.append((name, copy.deepcopy(arguments)))
        return f"Resultado real de {name}"

    monkeypatch.setattr(tools, "executar_ferramenta", execute)

    class Model:
        def create_chat_completion(self, **kwargs):
            # Cancellation callbacks may own locks and cannot be deep-copied.
            requests.append(
                copy.deepcopy({k: v for k, v in kwargs.items() if k != "should_cancel"})
            )
            assert replies, "Unexpected LLM invocation"
            reply = replies.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            return iter(reply)

    class Manager:
        def route_and_invoke(self, *args, **kwargs):
            return "qwen3-8b-q4km", Model()

        def get_current_complexity(self):
            return "medium"

        def get_last_decision(self):
            return None

    monkeypatch.setattr(react, "get_multi_model_manager", Manager)

    def send(text, scope="conversation-a", agent_mode="executor", **kwargs):
        return engine.gerar_resposta(
            {
                "pergunta": text,
                "approval_scope": scope,
                "documento": "Fonte original: 42 unidades.",
                "nome_documento": "dados.txt",
                "memorias_relevantes": [],
                "agent_mode": agent_mode,
            },
            **kwargs,
        )

    return SimpleNamespace(
        send=send,
        replies=replies,
        calls=calls,
        requests=requests,
        store=AgentTaskStore(settings.data_dir / "agent_tasks.db"),
        settings=settings,
    )


def latest(h):
    return h.store.list("conversation-a")[0]


def test_task_retains_original_docx_across_approval_and_upload_cleanup(harness, tmp_path):
    from docx import Document

    import ai.engine as engine

    h = harness
    upload = tmp_path / "origem.docx"
    document = Document()
    document.add_paragraph("Nome: João da Silva")
    document.save(upload)
    original_bytes = upload.read_bytes()
    h.replies.extend([tool_reply("criar_editar_arquivo"), answer("Dados conferidos")])
    engine.gerar_resposta(
        {
            "pergunta": "TAREFA: Confira os dados e salve as informações",
            "approval_scope": "conversation-a",
            "agent_mode": "executor",
            "documento": "Nome: João da Silva",
            "nome_documento": "origem.docx",
            "documentos_anexados": [{"nome": "origem.docx", "caminho": str(upload)}],
        }
    )
    task = latest(h)
    assert task["status"] == "waiting_confirmation"
    retained = Path(task["prompt"]["documentos_anexados"][0]["caminho"])
    upload.unlink()
    assert retained.read_bytes() == original_bytes
    h.store = AgentTaskStore(h.store.path)
    h.send(f"AUTORIZAR {task['steps'][0]['approval_code']}")
    assert latest(h)["status"] == "completed"
    assert retained.read_bytes() == original_bytes
    assert any(
        str(retained) in message.get("content", "") for message in h.requests[-1]["messages"]
    )


def test_approval_resumes_original_goal_and_remaining_batch_after_reopen(harness):
    h = harness
    h.replies.extend([tool_reply("ler_teste", "criar_editar_arquivo", "ler_teste"), answer()])
    response = h.send("TAREFA: Leia os dados, salve e confira o relatorio")
    task = latest(h)
    assert task["status"] == "waiting_confirmation"
    assert [c[0] for c in h.calls] == ["ler_teste"]
    code = task["steps"][1]["approval_code"]
    assert f"AUTORIZAR {code}" in response
    # New store instance emulates reopened persistence, no in-memory approvals.
    h.store = AgentTaskStore(h.store.path)
    result = h.send(f"AUTORIZAR {code}")
    assert "Relatorio pronto" in result
    assert latest(h)["status"] == "completed"
    assert [c[0] for c in h.calls] == ["ler_teste", "criar_editar_arquivo", "ler_teste"]
    messages = h.requests[-1]["messages"]
    assert "42 unidades" in messages[1]["content"]
    assert [m["role"] for m in messages[-4:]] == ["assistant", "tool", "tool", "tool"]
    assert len({m["tool_call_id"] for m in messages if m["role"] == "tool"}) == 3
    h.send(f"AUTORIZAR {code}")
    assert len(h.calls) == 3


def test_approval_and_resume_cannot_cross_conversations(harness):
    h = harness
    h.replies.append(tool_reply("criar_editar_arquivo"))
    h.send("TAREFA: Salve os dados")
    task = latest(h)
    code = task["steps"][0]["approval_code"]
    h.send(f"AUTORIZAR {code}", scope="conversation-b")
    assert "nao encontrada" in h.send(f"RETOMAR {task['id']}", scope="conversation-b")
    assert task["id"] not in h.send("TAREFAS", scope="conversation-b")
    assert h.calls == []


def test_each_sensitive_action_requires_its_own_approval(harness):
    h = harness
    h.replies.extend([tool_reply("criar_editar_arquivo", "salvar_memoria"), answer()])
    h.send("TAREFA: Salve arquivo e memoria")
    first = latest(h)["steps"][0]["approval_code"]
    h.send(f"AUTORIZAR {first}")
    task = latest(h)
    assert task["status"] == "waiting_confirmation"
    assert len(h.calls) == 1
    h.send(f"AUTORIZAR {task['steps'][1]['approval_code']}")
    assert len(h.calls) == 2
    assert latest(h)["status"] == "completed"


def test_expired_approval_rotates_on_resume(harness):
    h = harness
    h.replies.append(tool_reply("criar_editar_arquivo"))
    h.send("TAREFA: Salve arquivo")
    task = latest(h)
    old = task["steps"][0]["approval_code"]
    task["steps"][0]["expires"] = time.time() - 1
    h.store.save(task)
    assert "expirada" in h.send(f"AUTORIZAR {old}")
    h.send(f"RETOMAR {task['id']}")
    assert latest(h)["steps"][0]["approval_code"] != old
    assert h.calls == []


def test_cancel_invalidates_pending_batch(harness):
    h = harness
    h.replies.append(tool_reply("criar_editar_arquivo", "ler_teste"))
    h.send("TAREFA: Salve e confira")
    task = latest(h)
    code = task["steps"][0]["approval_code"]
    h.send(f"CANCELAR {code}")
    h.send(f"AUTORIZAR {code}")
    h.send(f"RETOMAR {task['id']}")
    assert latest(h)["status"] == "cancelled"
    assert h.calls == []


def test_crash_with_uncertain_effect_never_replays(harness):
    h = harness
    h.replies.append(tool_reply("criar_editar_arquivo"))
    h.send("TAREFA: Salve arquivo")
    task = latest(h)
    task["status"] = "running"
    task["steps"][0]["status"] = "running"
    task["steps"][0].pop("approval_code")
    h.store.save(task)
    assert "resultado desconhecido" in h.send(f"RETOMAR {task['id']}")
    assert latest(h)["status"] == "paused"
    h.send(f"RETOMAR {task['id']}")
    assert h.calls == []


def test_a_spent_slice_continues_without_replaying_completed_tools(harness, monkeypatch):
    import ai.react as react

    h = harness
    monkeypatch.setattr(react, "MAX_ITERACOES_TAREFA", 1)
    h.replies.extend([tool_reply("ler_teste"), answer()])
    response = h.send("TAREFA: Leia e resuma")
    # The turn budget is spent right after the tool ran.  A large document
    # outlives one slice, so the task continues in the same reply instead of
    # asking for RETOMAR -- and the executed step is not replayed.
    assert "Relatorio pronto" in response
    assert latest(h)["status"] == "completed"
    assert len(h.calls) == 1
    # RETOMAR on a completed task only reports it; nothing runs twice.
    h.send(f"RETOMAR {latest(h)['id']}")
    assert len(h.calls) == 1


def test_cancelled_stream_restarts_from_checkpoint(harness):
    h = harness
    h.replies.extend([answer("Texto parcial"), answer("Resposta completa")])
    cancel = threading.Event()
    h.send("TAREFA: Analise os dados", fn_chunk=lambda _: cancel.set(), should_cancel=cancel.is_set)
    task = latest(h)
    # A user-initiated stop is a cancellation, not an ambiguous failure — and
    # an explicit RETOMAR is what brings it back from the checkpoint.
    assert task["status"] == "cancelled"
    assert "Resposta completa" in h.send(f"RETOMAR {task['id']}")


def test_repeated_tools_pause_without_automatic_restart(harness):
    h = harness
    h.replies.extend([tool_reply("ler_teste") for _ in range(15)])
    response = h.send("TAREFA: Analise os dados")
    assert "Sem progresso" in response
    assert latest(h)["status"] == "paused"
    assert len(h.requests) < 10


def test_no_progress_guard_ignores_changing_call_ids(harness):
    from ai.task_runtime import TaskPausedError, TaskSession

    h = harness
    task = h.store.create("conversation-a", {"pergunta": "Analise os dados"}, mode="executor")
    session = TaskSession(h.store, task, settings=h.settings)
    messages = []
    for i in range(3):
        messages.append(
            {"role": "assistant", "content": "Mesma hipótese", "tool_calls": [{"id": str(i)}]}
        )
        session.before_model(messages, [], 16384)
    messages.append(
        {"role": "assistant", "content": "Mesma hipótese", "tool_calls": [{"id": "new"}]}
    )
    with pytest.raises(TaskPausedError, match="Sem progresso"):
        session.before_model(messages, [], 16384)
    assert h.store.get(task["id"], "conversation-a")["status"] == "paused"


def test_truncated_model_output_is_not_task_completion(harness):
    h = harness
    h.replies.extend(
        [answer("Parte do relatório") + [{"choices": [{"delta": {}, "finish_reason": "length"}]}]]
    )
    response = h.send("TAREFA: Analise os dados")
    task = latest(h)
    assert task["status"] == "paused"
    assert "limite de tokens" in response
    assert "Parte do relatório" in task["output"]


def test_read_success_does_not_verify_requested_inventory_write(harness):
    from ai.task_runtime import TaskSession

    h = harness
    task = h.store.create(
        "conversation-a", {"pergunta": "Dê entrada em 5 peças no estoque"}, mode="executor"
    )
    task["steps"] = [{"tool": "listar_estoque", "status": "succeeded", "result": "5 peças"}]
    session = TaskSession(h.store, task, settings=h.settings)
    assert not session.finish("Entrada realizada")
    assert task["status"] == "failed" and "não foi confirmada" in task["error"]


def test_report_about_stock_entries_does_not_require_new_entry(harness):
    from ai.task_runtime import TaskSession

    h = harness
    task = h.store.create(
        "conversation-a",
        {"pergunta": "Analise as movimentações de entrada de peças no estoque"},
        mode="executor",
    )
    task["steps"] = [
        {"tool": "historico_movimentacoes", "status": "succeeded", "result": "5 peças"}
    ]
    session = TaskSession(h.store, task, settings=h.settings)
    assert session.finish("5 peças recebidas.")


def test_prose_from_every_turn_survives_in_the_answer(harness):
    # A long batch writes in several turns.  Each turn's buffer is reset (it also
    # carries the tool-call payload), so without accumulation the answer would
    # collapse to the last turn and the scope would look tiny.
    h = harness
    h.replies.extend(
        [
            prose_with_tool("Secao 1: resumo do primeiro texto.", "ler_teste"),
            prose_with_tool("Secao 2: resumo do segundo texto.", "ler_teste"),
            answer("Secao 3: conclusao."),
        ]
    )
    response = h.send("TAREFA: Compare o lote de trabalho")
    for trecho in ("Secao 1", "Secao 2", "Secao 3"):
        assert trecho in response
    assert latest(h)["status"] == "completed"


def test_a_task_may_run_the_tools_the_local_gate_requires(harness, monkeypatch):
    # "processos" is a Celsius-owned domain: the model may not answer from
    # prior knowledge.  The gate injects listar_processos_prazos itself, so that
    # tool must be authorized for the step -- otherwise every injected step
    # fails validation and the task burns its whole turn budget re-queueing it.
    import ai.tools as tools_module
    from core import tool_policy

    monkeypatch.setitem(
        tool_policy._POLICIES,
        "listar_processos_prazos",
        tool_policy.ToolPolicy(tool_policy.Risk.READ, "Leitura de prazos."),
    )
    registered = SimpleNamespace(
        nome="listar_processos_prazos",
        descricao="Lista processos",
        schema={"type": "object", "properties": {}},
        executar=lambda: None,
    )
    monkeypatch.setattr(
        tools_module,
        "obter_ferramenta",
        lambda name: registered if name == "listar_processos_prazos" else None,
    )
    h = harness
    h.replies.extend([answer("Resumo dos prazos."), answer("Fechamento.")])
    response = h.send("TAREFA: Resuma os processos em aberto")
    assert "Resumo dos prazos" in response
    task = latest(h)
    assert ("listar_processos_prazos", "succeeded") in [
        (step["tool"], step["status"]) for step in task["steps"]
    ]
    assert task["status"] == "completed"


def test_approval_replies_count_as_task_turns():
    from ai.task_runtime import is_task_command

    # A task stopped on a confirmation must keep its streamed work when the user
    # answers, so the UI has to recognise the approval forms as task turns too.
    assert is_task_command("AUTORIZAR ABC123")
    assert is_task_command("CANCELAR ABC123")
    assert is_task_command("RETOMAR 94b7d7f5f757")
    assert is_task_command("TAREFA: algo")
    assert not is_task_command("AUTORIZAR o pedido")
    assert not is_task_command("resuma os documentos")


def test_a_task_stops_continuing_when_the_total_time_is_spent(harness, monkeypatch):
    import ai.task_runtime as task_runtime

    h = harness
    # Use the default task budget (12 iterations) since monkeypatching the budget
    # is fragile due to import-order issues. The test still validates the timeout
    # behavior: after the first slice exhausts its budget, the wall-clock check
    # (MAX_TASK_SECONDS_TOTAL=0) must pause the task with the expected message.
    monkeypatch.setattr(task_runtime, "MAX_TASK_SECONDS_TOTAL", 0)
    # Provide enough replies for the first slice (default budget = 12 iterations).
    # Each iteration consumes one reply; a tool call round-trip uses two.
    # Keep making distinct progress so the no-progress brake does not mask the
    # wall-clock limit this test specifically exercises.
    h.replies.extend([prose_with_tool(f"Secao {i + 1}: inicio.", "ler_teste") for i in range(12)])
    response = h.send("TAREFA: Escreva o capitulo")
    assert "Secao 1" in response
    assert "Tempo maximo" in response
    assert latest(h)["status"] == "paused"


def test_a_task_awaiting_confirmation_reports_the_reason_below_its_work(harness):
    # A pause the user must act on is not resumed automatically.  The status is
    # a footer, not the message: the work already done stays readable and the
    # prompt for the code appears below it.
    h = harness
    h.replies.append(prose_with_tool("Secao 1: ja convertida.", "criar_editar_arquivo"))
    response = h.send("TAREFA: Converta o lote de trabalho")
    assert "Secao 1" in response
    assert "AUTORIZAR" in response
    assert response.index("Secao 1") < response.index("AUTORIZAR")
    assert latest(h)["status"] == "waiting_confirmation"


def test_a_resumed_slice_keeps_the_previous_trajectory(harness, monkeypatch):
    import ai.react as react

    h = harness
    monkeypatch.setattr(react, "MAX_ITERACOES_TAREFA", 1)
    h.replies.append(prose_with_tool("Secao 1: ja convertida.", "ler_teste"))
    h.send("TAREFA: Converta o lote de trabalho")
    task = latest(h)
    h.replies.append(answer("Secao 2: concluida."))
    response = h.send(f"RETOMAR {task['id']}")
    assert "Secao 1" in response
    assert "Secao 2" in response
    assert latest(h)["status"] == "completed"


def test_out_of_scope_tool_is_not_executed(harness):
    h = harness
    h.replies.extend([tool_reply("excluir_tudo"), answer("Nao foi possivel")])
    h.send("TAREFA: Analise os dados")
    assert h.calls == []
    assert latest(h)["steps"][0]["status"] == "failed"


def test_normal_chat_does_not_create_tasks(harness):
    assert harness.send("obrigado", scope="")
    assert harness.store.list("conversation-a") == []


def test_total_budget_is_not_reset_by_resume(harness, monkeypatch):
    import ai.react as react
    import ai.task_runtime as runtime

    h = harness
    # A turn budget smaller than the loop, so the budget guard is what stops the
    # task — that is the spend the resume must not hand back.
    monkeypatch.setattr(react, "MAX_ITERACOES_TAREFA", 5)
    monkeypatch.setattr(runtime, "MAX_TASK_ITERATIONS", 1)
    h.replies.append(tool_reply("ler_teste"))
    h.send("TAREFA: Leia e resuma")
    task = latest(h)
    assert task["status"] == "failed"
    h.send(f"RETOMAR {task['id']}")
    assert len(h.requests) == 1


def test_task_budget_is_frozen_from_its_mode(harness, monkeypatch):
    from core.agent_modes import get_mode

    h = harness
    import ai.task_runtime as runtime

    mode = get_mode("executor")
    h.replies.extend([tool_reply("ler_teste"), answer()])
    h.send("TAREFA: Leia e resuma")
    task = latest(h)
    assert task["mode"] == "executor"
    assert task["limits"] == {
        "max_iterations": mode.max_iterations,
        "max_steps": mode.max_steps,
        "max_seconds": mode.max_seconds,
    }

    # Retomar a finished task never rewrites its frozen budget, and the tighter
    # global ceiling is applied when the *next* task is created.
    monkeypatch.setattr(runtime, "MAX_TASK_ITERATIONS", 1)
    h.send(f"RETOMAR {task['id']}")
    assert (
        h.store.get(task["id"], "conversation-a")["limits"]["max_iterations"] == mode.max_iterations
    )

    h.replies.append(tool_reply("ler_teste"))
    h.send("TAREFA: Leia e resuma")
    assert latest(h)["limits"]["max_iterations"] == 1


def test_a_global_ceiling_can_only_tighten_a_mode_budget(harness, monkeypatch):
    import ai.task_runtime as runtime

    h = harness
    monkeypatch.setattr(runtime, "SLICE_SECONDS", 30)
    h.replies.append(answer())
    h.send("TAREFA: Responda sem usar ferramentas")
    assert latest(h)["limits"]["max_seconds"] == 30


def test_a_mode_that_cannot_plan_refuses_the_task(harness):
    from core.agent_modes import get_mode

    h = harness
    response = h.send("TAREFA: Leia e resuma", agent_mode="assistente")
    assert "nao executa tarefas autonomousas" in response
    assert h.store.list("conversation-a") == []
    assert get_mode("assistente").can_plan is False


def test_a_task_starts_in_planning_until_it_queues_a_tool(harness):
    h = harness
    h.replies.extend([tool_reply("ler_teste"), answer()])
    h.send("TAREFA: Leia e resuma")
    assert latest(h)["status"] == "completed"
    assert latest(h)["steps"][0]["status"] == "succeeded"


def test_research_task_cannot_complete_without_web_evidence(harness):
    h = harness
    h.replies.extend([answer("Encontrei as noticias mais relevantes."), answer("Sem fontes.")])
    response = h.send(
        "TAREFA: Liste as noticias mais relevantes de inteligencia artificial da semana passada"
    )
    task = latest(h)
    assert task["status"] == "failed"
    assert "nenhuma fonte web" in task["error"]
    assert "[failed]" in response


def test_news_task_promotes_executor_to_researcher(harness):
    h = harness
    h.replies.extend([answer("Sem fontes."), answer("Sem fontes.")])
    h.send("TAREFA: Liste as noticias de inteligencia artificial da semana passada")
    task = latest(h)
    assert task["mode"] == "pesquisador"
