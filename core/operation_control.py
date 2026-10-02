"""Cooperative cancellation and bounded waits without orphan native locks."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from time import monotonic

from core.turn_metrics import phase


class OperationCancelled(BaseException):
    pass


class OperationTimeoutError(RuntimeError):
    pass


_control = ContextVar("celsius_operation_control", default=(None, None))


@contextmanager
def bind_control(should_cancel, deadline=None):
    previous_cancel, previous_deadline = _control.get()
    if previous_cancel:
        callback = should_cancel

        def should_cancel():
            return previous_cancel() or bool(callback and callback())

    if previous_deadline is not None:
        deadline = previous_deadline if deadline is None else min(deadline, previous_deadline)
    token = _control.set((should_cancel, deadline))
    try:
        yield
    finally:
        _control.reset(token)


def propagate_control(function):
    call_signature = signature(function)

    @wraps(function)
    def controlled(*args, **kwargs):
        arguments = call_signature.bind_partial(*args, **kwargs).arguments
        prompt = arguments.get("prompt_dict") or {}
        should_cancel = arguments.get("should_cancel")
        check_control(should_cancel)
        deadline = prompt.get("deadline")
        if deadline is None:
            from core.message_intent import classify_intent

            intent = classify_intent(
                prompt.get("pergunta", arguments.get("pergunta", "")),
                has_attachment=bool(
                    prompt.get("documento")
                    or prompt.get("anexos")
                    or prompt.get("caminho_imagem")
                    or arguments.get("caminho_imagem")
                ),
            )
            deadline = deadline_for_intent(intent.kind, prompt.get("agent_mode"))
        with bind_control(should_cancel, deadline):
            check_control()
            return function(*args, **kwargs)

    return controlled


def deadline_for_intent(kind, mode=None):
    if kind in {"task", "control"}:
        seconds = 3600
    elif kind in {"general", "conversation"}:
        seconds = 120
    else:
        from core.agent_modes import get_mode

        seconds = get_mode(mode).max_seconds
    return monotonic() + seconds


def check_control(should_cancel=None, deadline=None):
    bound_cancel, bound_deadline = _control.get()
    if (should_cancel and should_cancel()) or (bound_cancel and bound_cancel()):
        raise OperationCancelled()
    if bound_deadline is not None:
        deadline = bound_deadline if deadline is None else min(deadline, bound_deadline)
    if deadline is not None and monotonic() >= deadline:
        raise OperationTimeoutError(
            "Limite de tempo atingido; a operação foi interrompida sem concluir."
        )


def acquire_cancellable(lock, *, should_cancel=None, deadline=None, phase_name="lock_wait"):
    with phase(phase_name):
        while True:
            check_control(should_cancel, deadline)
            if lock.acquire(timeout=0.05):
                try:
                    check_control(should_cancel, deadline)
                except BaseException:
                    lock.release()
                    raise
                return


@contextmanager
def cancellable_lock(lock, *, should_cancel=None, deadline=None):
    acquire_cancellable(lock, should_cancel=should_cancel, deadline=deadline)
    try:
        yield
    finally:
        lock.release()
