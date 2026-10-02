"""HTTP contracts for the agentic surface: modes, tool policy and Jev health.

Everything here is read-only and cheap, so a client can render the mode picker,
show the real confirmation policy and display the Jev status without guessing.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.agent_modes import MODES_BY_ID, get_mode, is_valid_mode, list_modes
from core.agent_tasks import TASK_STATES, AgentTaskStore, normalize_state
from core.chat_service import ChatBusyError, ChatNotFoundError
from core.decisions import get_decision_client
from core.tool_policy import policy_table

router = APIRouter(tags=["agentic modes"])


class ModeRequest(BaseModel):
    mode: str = Field(min_length=1, max_length=40)


class ConfirmRequest(BaseModel):
    approval_code: str = Field(min_length=1, max_length=20)


class ScheduleRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=10_000)
    mode: str = Field(default="executor", min_length=1, max_length=40)
    every_seconds: int = Field(default=3600, ge=60, le=31_536_000)


def _store(request: Request) -> AgentTaskStore:
    settings = request.app.state.settings
    return AgentTaskStore(settings.data_dir / "agent_tasks.db")


def _run_store(request: Request):
    from ai.multi_agent import AgentRunStore

    return AgentRunStore(request.app.state.settings.data_dir)


@router.get("/agents/modes")
def agent_modes() -> dict:
    """Catalog of selectable modes plus the task lifecycle they can reach."""
    return {
        "ok": True,
        "items": list_modes(),
        "default": MODES_BY_ID["assistente"].id,
        "task_states": list(TASK_STATES),
    }


@router.get("/agents/modes/{mode_id}")
def agent_mode_detail(mode_id: str) -> dict:
    """One mode with its effective (clamped) execution limits."""
    if not is_valid_mode(mode_id):
        raise HTTPException(status_code=404, detail="Modo desconhecido.")
    from core.settings import get_settings

    ceilings = get_settings().agent
    mode = get_mode(mode_id)
    return {
        "ok": True,
        "mode": mode.as_dict(),
        "limits": mode.limits(
            ceiling_steps=ceilings.max_steps,
            ceiling_seconds=ceilings.max_seconds,
            ceiling_attempts=ceilings.max_attempts,
            ceiling_iterations=ceilings.max_iterations,
        ),
    }


@router.get("/agents/tools")
def agent_tool_policy() -> dict:
    """The deterministic risk table every surface should agree on."""
    return {"ok": True, "items": policy_table().as_list()}


@router.get("/agents/health")
def agent_health() -> dict:
    """Reachability of the local decision server (never raises)."""
    return {"ok": True, "decision": get_decision_client().health().as_dict()}


def _schedule_store(request: Request):
    from core.agent_schedule import AgentScheduleStore

    return AgentScheduleStore(request.app.state.settings.data_dir)


@router.get("/agents/schedules")
def agent_schedules(request: Request, scope: str = "") -> dict:
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    return {"ok": True, "items": _schedule_store(request).list(scope)}


@router.post("/agents/schedules")
def agent_schedule_create(payload: ScheduleRequest, request: Request, scope: str = "") -> dict:
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    if not is_valid_mode(payload.mode) or not get_mode(payload.mode).can_plan:
        raise HTTPException(status_code=400, detail="Escolha um modo executor valido.")
    # Verifies the conversation before a schedule can target it.
    try:
        request.app.state.chat_coordinator.get_conversation(scope)
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    item = _schedule_store(request).create(
        scope=scope,
        objective=payload.objective,
        mode=payload.mode,
        every_seconds=payload.every_seconds,
    )
    return {"ok": True, "schedule": item}


@router.post("/agents/schedules/{schedule_id}/enabled")
def agent_schedule_enabled(
    schedule_id: str, request: Request, scope: str = "", enabled: bool = True
) -> dict:
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    item = _schedule_store(request).set_enabled(schedule_id, scope, enabled)
    if not item:
        raise HTTPException(status_code=404, detail="Agendamento nao encontrado.")
    return {"ok": True, "schedule": item}


@router.get("/agents/tasks")
def agent_tasks(request: Request, scope: str = "", limit: int = 20) -> dict:
    """Durable tasks of one conversation, using the shared state vocabulary."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    tasks = _store(request).list(scope, limit=limit)
    return {
        "ok": True,
        "items": [
            {
                "id": task["id"],
                "status": task["status"],
                "mode": task.get("mode", ""),
                "objective": task.get("objective", ""),
                "error": task.get("error", ""),
                "updated": task.get("updated", 0),
                "pending_approvals": [
                    step.get("approval_code")
                    for step in task.get("steps", [])
                    if step.get("approval_code")
                ],
            }
            for task in tasks
        ],
    }


@router.get("/agents/runs")
def agent_runs(request: Request, scope: str = "", limit: int = 20) -> dict:
    """Durable Work-mode supervisor runs and their independent workers."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    return {"ok": True, "items": _run_store(request).list(scope, limit=limit)}


@router.get("/agents/runs/{run_id}")
def agent_run_detail(run_id: str, request: Request, scope: str = "") -> dict:
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    run = _run_store(request).get(run_id, scope)
    if run is None:
        raise HTTPException(status_code=404, detail="Execucao multiagente nao encontrada.")
    return {"ok": True, "run": run}


@router.post("/agents/mode")
def agent_select_mode(payload: ModeRequest, request: Request) -> dict:
    """Persist the mode chosen for a conversation.

    Silence never confirms: this endpoint only records an explicit choice.
    """
    if not is_valid_mode(payload.mode):
        raise HTTPException(status_code=400, detail="Modo desconhecido.")
    scope = str(request.query_params.get("scope", "")).strip()
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    mode = get_mode(payload.mode)
    _store(request).set_mode(scope, mode.id)
    request.app.state.event_hub.publish(
        "agent.mode_changed",
        {"scope": scope, "mode": mode.id, "label": mode.label},
    )
    return {"ok": True, "mode": mode.id, "label": mode.label}


@router.get("/agents/tasks/{task_id}")
def agent_task_detail(task_id: str, request: Request, scope: str = "") -> dict:
    """Get full task details including plan and all steps."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    task = _store(request).get(task_id, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada.")
    return {
        "ok": True,
        "task": {
            "id": task["id"],
            "status": normalize_state(task.get("status", "unknown")),
            "mode": task.get("mode", ""),
            "objective": task.get("objective", ""),
            "plan": task.get("plan", []),
            "steps": task.get("steps", []),
            "result": task.get("result", ""),
            "error": task.get("error", ""),
            "created": task.get("created", 0),
            "updated": task.get("updated", 0),
            "limits": task.get("limits", {}),
            "workspace": task.get("workspace", ""),
            "verification": task.get("verification", {}),
        },
    }


@router.get("/agents/tasks/{task_id}/plan")
def agent_task_plan(task_id: str, request: Request, scope: str = "") -> dict:
    """Get the task plan."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    task = _store(request).get(task_id, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada.")
    return {
        "ok": True,
        "plan": task.get("plan", []),
    }


@router.get("/agents/tasks/{task_id}/steps")
def agent_task_steps(task_id: str, request: Request, scope: str = "") -> dict:
    """Get all steps with their current status."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    task = _store(request).get(task_id, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada.")
    steps = task.get("steps", [])
    current_step = None
    for step in steps:
        status = normalize_state(step.get("status", "planned"))
        if status in ("running", "waiting_confirmation", "awaiting_approval", "authorized"):
            current_step = step
            break
    return {
        "ok": True,
        "steps": [
            {
                "index": i,
                "call_id": step.get("call_id"),
                "tool": step.get("tool"),
                "arguments": step.get("arguments"),
                "status": normalize_state(step.get("status", "planned")),
                "allowed": step.get("allowed", False),
                "result": step.get("result"),
                "approval_code": step.get("approval_code"),
                "expires": step.get("expires"),
            }
            for i, step in enumerate(steps)
        ],
        "current_step_index": steps.index(current_step) if current_step else -1,
    }


@router.post("/agents/tasks/{task_id}/confirm")
def agent_task_confirm(
    task_id: str, payload: ConfirmRequest, request: Request, scope: str = ""
) -> dict:
    """Confirm a pending action (approve)."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    store = _store(request)
    task = store.find_approval(payload.approval_code, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Aprovacao nao encontrada ou expirada.")
    if task["id"] != task_id:
        raise HTTPException(status_code=400, detail="Aprovacao nao pertence a esta tarefa.")
    step = next(
        (s for s in task["steps"] if s.get("approval_code") == payload.approval_code.upper()), None
    )
    if not step:
        raise HTTPException(status_code=404, detail="Passo nao encontrado.")
    if step.get("expires", 0) <= time.time():
        raise HTTPException(status_code=400, detail="Aprovacao expirada.")
    step["status"] = "authorized"
    store.save(task)

    # Approval is an explicit user action, so continue the durable task through
    # the same serial chat coordinator used by the regular UI.  This preserves
    # one-inference-at-a-time limits and makes API approvals behave like the
    # desktop command ``AUTORIZAR <codigo>``.
    try:
        job = request.app.state.chat_coordinator.submit(
            message=f"RETOMAR {task_id}",
            conversation_id=scope,
            agent_mode=task.get("mode", ""),
        )
    except ChatBusyError as exc:
        # The authorization remains durable; a later RETOMAR will consume it.
        return {
            "ok": True,
            "task_id": task_id,
            "resumed": False,
            "message": f"Acao autorizada. {exc}",
        }
    except ChatNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "ok": True,
        "task_id": task_id,
        "resumed": True,
        "job": job,
        "message": "Acao autorizada e tarefa retomada.",
    }


@router.post("/agents/tasks/{task_id}/cancel")
def agent_task_cancel(task_id: str, request: Request, scope: str = "") -> dict:
    """Cancel a task."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    store = _store(request)
    task = store.get(task_id, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada.")
    task["status"] = "cancelled"
    task["error"] = "Tarefa cancelada via API."
    store.save(task)
    return {"ok": True, "task_id": task_id, "message": "Tarefa cancelada."}


@router.get("/agents/tasks/{task_id}/artifacts")
def agent_task_artifacts(task_id: str, request: Request, scope: str = "") -> dict:
    """Return deterministic evidence for files produced by a task."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    task = _store(request).get(task_id, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada.")
    from core.agent_artifacts import verify_task

    verification = verify_task(task, request.app.state.settings.data_dir)
    task["verification"] = verification
    _store(request).save(task)
    return {"ok": True, "task_id": task_id, "workspace": task.get("workspace", ""), **verification}


@router.get("/agents/tasks/{task_id}/history")
def agent_task_history(task_id: str, request: Request, scope: str = "") -> dict:
    """Get task history (same as detail but focused on execution log)."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    task = _store(request).get(task_id, scope)
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa nao encontrada.")
    steps = task.get("steps", [])
    return {
        "ok": True,
        "history": [
            {
                "timestamp": step.get("created", task.get("created", 0)),
                "step_index": i,
                "tool": step.get("tool"),
                "status": normalize_state(step.get("status", "planned")),
                "arguments_summary": str(step.get("arguments", {}))[:200],
                "result_summary": str(step.get("result", ""))[:200],
                "approval_code": step.get("approval_code"),
            }
            for i, step in enumerate(steps)
        ],
    }


@router.get("/agents/mode/current")
def agent_current_mode(request: Request, scope: str = "") -> dict:
    """Get the currently active agent mode for a conversation."""
    if not scope:
        raise HTTPException(status_code=400, detail="Informe a conversa (scope).")
    store = _store(request)
    mode_id = store.get_stored_mode(scope)
    if not mode_id:
        # Compatibility for tasks created before conversation preferences existed.
        tasks = store.list(scope, limit=1)
        mode_id = tasks[0].get("mode", "assistente") if tasks else "assistente"
    mode = get_mode(mode_id)
    return {"ok": True, "mode": mode.id, "label": mode.label}
