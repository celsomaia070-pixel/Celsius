"""Opt-in, serial local tasks using the existing ReAct engine and tools.

The execution lock spans inference and effects; SQLite writes do not. An effect
is marked running BEFORE invocation. A crash in that interval requires review,
because a generic tool cannot guarantee exactly-once external side effects.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.agent_modes import get_mode, resolve_mode
from core.agent_tasks import AgentTaskStore, normalize_state
from core.json_persistence import locked_path
from core.tool_approval import (
    APPROVAL_REQUIRED_PREFIX,
    PendingToolApproval,
    approval_message,
)
from core.tool_policy import assess_tool, summarize_arguments

#: Hard backstops for one task.  A mode's own budget is authoritative; these only
#: keep a misconfigured mode from running unbounded.  Both are far above the turn
#: count a large document batch needs, because a batch's cost is dominated by
#: inference, not by the number of tool calls it issues.
MAX_TASK_ITERATIONS = 200
MAX_TASK_STEPS = 240
#: Seconds a single slice may run before it pauses and asks to be resumed.  A
#: pause is not a failure: the accumulated output is kept and the next slice
#: continues the same trajectory.
SLICE_SECONDS = 900
#: Wall clock one task may consume in total, across every slice and across app
#: restarts (``spent_seconds`` is persisted).  It bounds the automatic
#: continuation below so a single reply can never hang the interface, while
#: being long enough for a full document batch on this hardware.
MAX_TASK_SECONDS_TOTAL = 3600
#: Only a spent budget is worth resuming on its own.  A confirmation, a rejected
#: action, a cancelled tool or an unknown effect must always reach the user.
_MOTIVOS_CONTINUAVEIS = (
    "Limite de tempo desta execucao atingido",
    "Limite de etapas desta execucao atingido",
)


@dataclass(frozen=True)
class TaskLimits:
    """Effective budget for one task, after the mode's own ceiling is applied."""

    max_iterations: int
    max_steps: int
    max_seconds: int


def resolve_task_limits(task: dict, settings=None) -> TaskLimits:
    """Clamp the mode's limits to the global hard ceilings.

    A stored task keeps its original budget when resumed, so raising a mode's
    limits later cannot resurrect a spent budget mid-flight.
    """
    mode = get_mode(task.get("mode"))
    stored = task.get("limits") or {}
    return TaskLimits(
        max_iterations=_positive(
            stored.get("max_iterations"), mode.max_iterations, MAX_TASK_ITERATIONS
        ),
        max_steps=_positive(stored.get("max_steps"), mode.max_steps, MAX_TASK_STEPS),
        max_seconds=_positive(stored.get("max_seconds"), mode.max_seconds, SLICE_SECONDS),
    )


def _positive(value, fallback: int, ceiling: int) -> int:
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        candidate = int(fallback)
    return max(1, min(candidate, ceiling))


class TaskPausedError(Exception):
    pass


class TaskBusyError(Exception):
    pass


_RESEARCH_TOOLS = {"pesquisar_web", "pesquisar_google", "pesquisar_noticias", "navegar_web"}


def _has_verifiable_web_evidence(result: object) -> bool:
    """Return whether a tool result contains an actual web source URL."""
    text = str(result or "")
    if not text or text.lower().startswith(("erro", "nenhuma fonte web")):
        return False
    return bool(re.search(r"https?://[^\s)\]>]+", text, re.IGNORECASE))


def requires_research_evidence(task: dict) -> bool:
    """Identify objectives whose completion must be backed by a web step."""
    objective = str(task.get("objective") or task.get("prompt", {}).get("pergunta", "")).lower()
    markers = (
        "noticia",
        "notícias",
        "news",
        "atual",
        "recente",
        "semana passada",
        "pesquis",
        "internet",
        "web",
        "google",
        "aconteceu",
        "previsao",
        "previsão",
        "tempo",
        "clima",
        "meteorolog",
    )
    return any(marker in objective for marker in markers)


@contextmanager
def _execution_lock(path):
    with ExitStack() as stack:
        try:
            stack.enter_context(locked_path(path, timeout=0.1))
        except TimeoutError as exc:
            raise TaskBusyError() from exc
        yield


def _com_relatorio(task: dict, motivo: str, *, retomar: bool = False) -> str:
    """Render a task's accumulated output with the reason as a footer.

    The prose every turn produced *is* the answer the user needs, so it leads the
    message; the status line only explains why the run stopped.  Reporting the
    status alone would erase the trajectory of a long task, which is exactly what
    a large document batch produces.
    """
    saida = str(task.get("output") or "").strip()
    rodape = f"Tarefa {task.get('id', '')} [{task.get('status', '')}]."
    partes = [p for p in (saida, motivo.strip(), rodape) if p]
    if retomar:
        partes.append(f"RETOMAR {task.get('id', '')}")
    return "\n\n".join(partes)


class TaskSession:
    def __init__(self, store, task, *, should_cancel=None, fn_status=None, settings=None):
        self.store = store
        self.task = task
        self.should_cancel = should_cancel
        self.fn_status = fn_status
        self.limits = resolve_task_limits(task, settings)
        self.deadline = time.monotonic() + self.limits.max_seconds
        #: Prose the ReAct engine has produced so far.  The engine refreshes it
        #: on every turn, so a pause raised by any guard can still report the
        #: work done instead of an empty answer.
        self.output = str(task.get("output") or "")

    def save(self):
        self.task["output"] = self.output
        self.store.save(self.task)

    def pause(self, reason, status="paused"):
        self.task["status"] = normalize_state(status)
        self.task["error"] = reason
        self.save()
        raise TaskPausedError(reason)

    def check(self):
        if self.should_cancel and self.should_cancel():
            self.task["status"] = "cancelled"
            self.task["error"] = "Execucao cancelada; o progresso foi salvo."
            self.save()
            raise TaskPausedError(self.task["error"])
        if time.monotonic() >= self.deadline:
            self.pause("Limite de tempo desta execucao atingido.")

    def before_model(self, messages, tools, context_size):
        from ai.context_budget import estimate_messages_tokens, estimate_tokens

        self.check()
        self.task["messages"] = messages
        if self.task["iterations"] >= self.limits.max_iterations:
            self.pause("Limite total de etapas de raciocinio atingido.", "failed")
        if (
            estimate_messages_tokens(messages) + estimate_tokens(json.dumps(tools))
            > context_size * 0.75
        ):
            self.pause(
                "Contexto da tarefa atingiu o limite; reduza o escopo em uma nova tarefa.",
                "failed",
            )
        self.task["iterations"] += 1
        self.save()

    def queue(self, messages, calls, allowed_tools):
        if len(self.task["steps"]) + len(calls) > self.limits.max_steps:
            self.pause("Limite total de ferramentas atingido.", "failed")
        self.task["messages"] = messages
        for call in calls:
            self.task["steps"].append(
                {
                    "call_id": call["id"],
                    "tool": call["function"]["name"],
                    "arguments": call["function"]["arguments"],
                    "status": "planned",
                    "allowed": call["function"]["name"] in allowed_tools,
                }
            )
        self.save()

    def drain(self):
        from ai.tool_result import ToolResult
        from ai.tools import _validate_tool_args, executar_ferramenta, obter_ferramenta
        from core.decisions import evaluate_tool_call, get_decision_client
        from core.settings import get_settings

        for step in self.task["steps"]:
            if step["status"] in {"succeeded", "failed", "cancelled"}:
                continue
            if step["status"] == "running":
                self.pause(
                    "Uma ferramenta foi interrompida com resultado desconhecido. "
                    "Confira os dados antes de iniciar outra tarefa; esta acao nao sera repetida.",
                    "paused",
                )
            self.check()
            tool = obter_ferramenta(step["tool"])
            args = step["arguments"]
            valid, error = (False, "Ferramenta fora do conjunto autorizado para esta etapa.")
            if tool and step["allowed"] and isinstance(args, dict):
                valid, error = _validate_tool_args(tool, args)
                if set(args) - set(tool.schema.get("properties", {})):
                    valid, error = False, "Argumentos desconhecidos."
            if not valid:
                self.record(step, f"Erro de validacao: {error}", failed=True)
                continue
            # Deterministic policy first, then Jev may only add a confirmation.
            sensitive = assess_tool(step["tool"], args).requires_confirmation
            if step["status"] == "authorized" and step.get("expires", 0) <= time.time():
                step["status"] = "awaiting_approval"
            if not sensitive and step["status"] != "authorized":
                client = get_decision_client()
                if client.enabled:
                    sensitive = evaluate_tool_call(
                        client, get_settings().decision, tool=step["tool"], arguments=args
                    ).requires_confirmation
            if sensitive and step["status"] != "authorized":
                if not step.get("approval_code") or step.get("expires", 0) <= time.time():
                    step["approval_code"] = secrets.token_hex(5).upper()
                    step["expires"] = time.time() + 300
                step["status"] = "awaiting_approval"
                pending = PendingToolApproval(
                    step["approval_code"], step["tool"], args, time.time(), self.task["scope"]
                )
                self.pause(
                    approval_message(pending).removeprefix(APPROVAL_REQUIRED_PREFIX).strip(),
                    "waiting_confirmation",
                )
            if self.fn_status:
                self.fn_status(f"Tarefa {self.task['id']}: executando {step['tool']}...")
            # Consume authorization before the effect. Never replay an uncertain effect.
            step.pop("approval_code", None)
            step["status"] = "running"
            self.save()
            result = executar_ferramenta(step["tool"], args)
            failed = not result.ok if isinstance(result, ToolResult) else str(result).startswith(("Erro", "Servico '"))
            self.record(step, str(result), failed=failed)

    def record(self, step, result, *, failed=False):
        step["status"] = "failed" if failed else "succeeded"
        step["result"] = result
        assessment = assess_tool(step["tool"], step.get("arguments", {}))
        try:
            from core.audit_log import AuditLogger

            AuditLogger(Path(self.store.path).parent / "agent_audit.jsonl").record_task_action(
                task_id=self.task["id"],
                mode=self.task.get("mode", ""),
                user=self.task.get("scope", ""),
                step=self.task["steps"].index(step),
                tool=step["tool"],
                args_summary=summarize_arguments(step.get("arguments", {})),
                jev_decision="confirmation" if step.get("approval_code") else "allowed",
                policy_decision=assessment.risk.value,
                confirmation="authorized"
                if step.get("status") == "succeeded" and assessment.requires_confirmation
                else None,
                result=result,
                error=result if failed else None,
            )
        except (OSError, ValueError):
            # Auditing must not hide the real tool result if local storage is full.
            pass
        self.task["messages"].append(
            {"role": "tool", "tool_call_id": step["call_id"], "content": result}
        )
        self.save()

    def finish(self, response):
        from core.agent_artifacts import task_requests_artifact, verify_task

        research_steps = [
            step
            for step in self.task.get("steps", [])
            if step.get("status") == "succeeded" and step.get("tool") in _RESEARCH_TOOLS
        ]
        if requires_research_evidence(self.task) and not any(
            _has_verifiable_web_evidence(step.get("result")) for step in research_steps
        ):
            self.task["verification"] = verify_task(self.task, Path(self.store.path).parent)
            self.task["status"] = "failed"
            self.task["error"] = (
                "A pesquisa nao foi concluida: nenhuma fonte web verificavel foi "
                "consultada. O Celsius nao deve apresentar noticias sem evidencia "
                "verificavel. Tente novamente com o modo Pesquisador e confirme "
                "que a conexao web esta disponivel."
            )
            self.task["result"] = ""
            self.save()
            return False

        self.task["verification"] = verify_task(self.task, Path(self.store.path).parent)
        objective = str(self.task.get("objective") or "").casefold()
        if task_requests_artifact(self.task) and re.search(r"\b(?:preench\w*|complet\w*)\b", objective):
            filled = False
            for step in self.task.get("steps", []):
                if step.get("status") != "succeeded" or step.get("tool") not in {
                    "preencher_documento", "preencher_documento_com_fontes",
                }:
                    continue
                try:
                    result, _ = json.JSONDecoder().raw_decode(str(step.get("result", "")).lstrip())
                except (ValueError, TypeError):
                    continue
                if isinstance(result, dict) and result.get("written") is True and Path(
                    str(result.get("output") or "")
                ).is_file():
                    filled = True
            if not filled:
                self.task["status"] = "failed"
                self.task["error"] = (
                    "O modelo solicitado nao foi preenchido. Um texto ou um relatorio novo "
                    "nao substitui a copia preenchida do documento anexado."
                )
                self.task["result"] = ""
                self.save()
                return False
        if task_requests_artifact(self.task) and not self.task["verification"]["artifact_count"]:
            self.task["status"] = "failed"
            self.task["error"] = (
                "Nenhum arquivo foi realmente criado para esta tarefa. O Celsius nao pode "
                "informar um caminho ou disponibilizar download sem um artefato verificavel."
            )
            self.task["result"] = ""
            self.save()
            return False
        self.task["status"] = "completed"
        self.task["result"] = response
        self.task["error"] = ""
        self.save()
        return True


def is_task_command(text: str) -> bool:
    """True when the text drives a task, including its approval replies.

    The approval forms matter as much as the creation forms: a task that stopped
    on a confirmation is still the same task, so its turn must keep the streamed
    work and append the outcome instead of replacing it with a short prompt.
    """
    return bool(
        re.match(
            r"^\s*(?:TAREFA\s*:|TAREFAS\s*$|RETOMAR\s+|CANCELAR\s+TAREFA\s+"
            r"|(?:AUTORIZAR|CANCELAR)\s+[A-Z0-9]{6,12}\s*$)",
            text,
            re.I,
        )
    )


def _executar_com_continuacao(
    task: dict,
    session: TaskSession,
    *,
    loop: Callable,
    fn_status=None,
    fn_passo=None,
    fn_chunk=None,
    should_cancel=None,
) -> str:
    """Drive the ReAct loop, continuing on its own when only a slice ran out.

    A large document outlives any single time slice, so a pause caused by the
    slice clock or by the turn budget is resumed inside the same reply instead
    of asking the user to type RETOMAR.  The overall wall clock stays bounded
    (MAX_TASK_SECONDS_TOTAL) and cancellation is honoured, so one turn cannot
    hang the interface.  Anything else -- a confirmation, a cancelled tool, an
    unknown effect -- is raised to the caller so it reaches the user.
    """
    inicio = time.monotonic()
    fatia = 1
    while True:
        try:
            session.drain()
            response, _ = loop(
                task["prompt"],
                fn_status=fn_status,
                fn_passo=fn_passo,
                fn_chunk=fn_chunk,
                history=task["prompt"].get("historico"),
                should_cancel=should_cancel,
                task_session=session,
            )
            if task["status"] not in {"completed", "failed", "cancelled"}:
                session.pause("Execucao pausada; o progresso foi salvo.")
            return response
        except TaskPausedError as exc:
            motivo = str(exc)
        continuavel = task["status"] == "paused" and any(
            motivo.startswith(m) for m in _MOTIVOS_CONTINUAVEIS
        )
        if not continuavel or (should_cancel and should_cancel()):
            raise TaskPausedError(motivo) from None
        gasto = task.get("spent_seconds", 0) + (time.monotonic() - inicio)
        if gasto >= MAX_TASK_SECONDS_TOTAL:
            task["spent_seconds"] = gasto
            session.save()
            raise TaskPausedError(
                f"Tempo maximo de {MAX_TASK_SECONDS_TOTAL // 60} minutos atingido nesta "
                "sessao; o progresso foi salvo."
            ) from None
        task["spent_seconds"] = gasto
        task["status"] = "running"
        task["error"] = ""
        session.save()
        inicio = time.monotonic()
        fatia += 1
        if fn_status:
            fn_status(f"Tarefa {task['id']}: continuando a execucao ({fatia})...")


def handle_task_command(
    prompt: dict,
    *,
    settings,
    loop: Callable,
    fn_status=None,
    fn_passo=None,
    fn_chunk=None,
    should_cancel=None,
) -> str | None:
    text = str(prompt.get("pergunta", "")).strip()
    approval = re.fullmatch(r"(AUTORIZAR|CANCELAR)\s+([A-Z0-9]{6,12})", text, re.I)
    if not is_task_command(text):
        return None
    scope = str(prompt.get("approval_scope", "")).strip()
    if not scope:
        return None if approval else "Abra uma conversa antes de criar uma tarefa."
    store = AgentTaskStore(Path(settings.data_dir) / "agent_tasks.db")
    try:
        # One task runner per data directory, also across desktop/web processes.
        with _execution_lock(store.path.with_suffix(".execution")):
            if text.upper() == "TAREFAS":
                items = store.list(scope)
                return "Tarefas desta conversa:\n" + (
                    "\n".join(f"- {t['id']} [{t['status']}]: {t['objective'][:160]}" for t in items)
                    or "Nenhuma tarefa criada."
                )
            if approval:
                action, code = approval.groups()
                task = store.find_approval(code, scope)
                if task is None:
                    return None  # Legacy approvals remain compatible.
                step = next(s for s in task["steps"] if s.get("approval_code") == code.upper())
                if action.upper() == "CANCELAR":
                    # Rejecting a pending action is a final decision: the step is
                    # closed and the task is not resumable, so the same effect can
                    # never be produced by a later RETOMAR.
                    step["status"] = "cancelled"
                    step.pop("approval_code", None)
                    task["status"] = "cancelled"
                    task["rejected_action"] = True
                    store.save(task)
                    return f"Tarefa {task['id']} cancelada. A acao pendente nao foi executada."
                if step["expires"] <= time.time():
                    return f"Autorizacao expirada. Envie RETOMAR {task['id']} para revisar a acao novamente."
                step["status"] = "authorized"
            elif text.upper().startswith("TAREFA"):
                objective = text.split(":", 1)[1].strip()
                if not objective:
                    return "Use TAREFA: seguida do objetivo e do resultado esperado."
                # The mode is resolved once, here, and stored on the task by
                # ``store.create`` below. Every later slice and iteration reuses
                # ``task["prompt"]["agent_mode"]``, so a long task cannot flip
                # lanes between turns while holding one workspace.
                mode_id = resolve_mode(objective, requested=prompt.get("agent_mode"))
                # Older web clients always sent ``executor`` for Work mode. A
                # current-data objective must still enter the web researcher
                # lane so the allowlist exposes real source tools. Kept as a
                # hard floor under the router: an objective that needs web
                # evidence can never end up in a mode without web tools.
                if mode_id == "executor" and requires_research_evidence({"objective": objective}):
                    mode_id = "pesquisador"
                if not get_mode(mode_id).can_plan:
                    return (
                        f"O modo {get_mode(mode_id).label} nao executa tarefas autonomousas. "
                        "Selecione Executor, Documentos, Estoque, Pesquisador ou Desenvolvedor."
                    )
                if prompt.get("caminho_imagem"):
                    return "Nesta primeira versao, use documentos com texto extraido em tarefas."
                # Persist extracted text; original attachments are retained in
                # task-owned inputs below before temporary uploads are cleaned.
                saved_prompt = {
                    key: prompt[key]
                    for key in (
                        "documento",
                        "nome_documento",
                        "memorias_relevantes",
                        "historico",
                        "system_prompt",
                    )
                    if key in prompt
                }
                saved_prompt.update(pergunta=objective, approval_scope=scope)
                saved_prompt["agent_mode"] = mode_id
                if requires_research_evidence({"objective": objective}):
                    research_instruction = (
                        "PESQUISA OBRIGATORIA: antes de responder, consulte uma ferramenta "
                        "web autorizada. A resposta somente pode apresentar noticias ou "
                        "fatos atuais acompanhada de URLs retornadas pela ferramenta. "
                        "Se nenhuma fonte verificavel for obtida, informe a falha e nao "
                        "apresente a informacao como confirmada."
                    )
                    existing_prompt = str(saved_prompt.get("system_prompt", "")).strip()
                    saved_prompt["system_prompt"] = (
                        f"{existing_prompt}\n{research_instruction}".strip()
                    )
                task = store.create(scope, saved_prompt, mode=mode_id)
                from core.chat_attachments import retain_task_document_attachments

                task["prompt"].update(retain_task_document_attachments(prompt, task["workspace"]))
                # Tell the model where task-owned outputs belong. The directory
                # is below the local data root and is later inventoried by the
                # deterministic artifact verifier.
                task["prompt"]["workspace"] = task["workspace"]
                # Freeze the budget now, so later edits to a mode cannot change
                # the limits of a task that is already running.
                limits = resolve_task_limits(task, settings)
                task["limits"] = {
                    "max_iterations": limits.max_iterations,
                    "max_steps": limits.max_steps,
                    "max_seconds": limits.max_seconds,
                }
                store.save(task)
            else:
                match = re.fullmatch(r"(RETOMAR|CANCELAR\s+TAREFA)\s+([a-f0-9]{12})", text, re.I)
                if not match:
                    return "Use RETOMAR <id> ou CANCELAR TAREFA <id>. Consulte os IDs com TAREFAS."
                task = store.get(match[2], scope)
                if task is None:
                    return "Tarefa nao encontrada nesta conversa."
                if match[1].upper().startswith("CANCELAR"):
                    task["status"] = "cancelled"
                    store.save(task)
                    return (
                        f"Tarefa {task['id']} cancelada; resultados anteriores foram preservados."
                    )
            # ``completed`` and ``failed`` are final: RETOMAR only reports them,
            # so a spent budget or a finished task can never silently re-run.
            # A cancelled task is resumable only when the user merely stopped the
            # stream; if they rejected a specific pending action, that decision
            # stands and RETOMAR only reports it.
            if task["status"] in {"completed", "failed"} or task.get("rejected_action"):
                return f"Tarefa {task['id']}: {task['status']}.\n{task['result'] or task['error']}".rstrip()
            session = TaskSession(
                store, task, should_cancel=should_cancel, fn_status=fn_status, settings=settings
            )
            # The model has not chosen its tools yet, so the task is planning.
            task["status"] = "planning" if not task["steps"] else "running"
            task["error"] = ""
            session.save()
            try:
                response = _executar_com_continuacao(
                    task,
                    session,
                    loop=loop,
                    fn_status=fn_status,
                    fn_passo=fn_passo,
                    fn_chunk=fn_chunk,
                    should_cancel=should_cancel,
                )
                if task["status"] != "completed":
                    detail = task.get("error") or response or "A tarefa nao foi concluida."
                    return _com_relatorio(task, detail)
                return f"{response}\n\nTarefa {task['id']} concluida."
            except TaskPausedError as exc:
                return _com_relatorio(task, str(exc), retomar=task["status"] == "paused")
            except BaseException:
                # A tool that was in flight when we died has an unknown effect:
                # never replay it silently, park the task for a human.
                task["status"] = (
                    "paused" if any(s["status"] == "running" for s in task["steps"]) else "failed"
                )
                task["error"] = "Execucao interrompida. Consulte o estado antes de continuar."
                session.save()
                raise
    except TaskBusyError:
        return "Ja existe uma tarefa em execucao. Aguarde ou interrompa a resposta atual."
