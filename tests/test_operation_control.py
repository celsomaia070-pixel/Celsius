"""Cancellation must interrupt lock waits and release streams on every exit."""

import threading
import time

import pytest

from core.inference_guard import LockedIterator
from core.operation_control import (
    OperationCancelled,
    OperationTimeoutError,
    acquire_cancellable,
    bind_control,
    cancellable_lock,
    check_control,
    propagate_control,
)
from core.turn_metrics import TurnMetrics, bind_metrics


def test_lock_wait_can_be_cancelled_without_releasing_another_owner():
    lock = threading.Lock()
    lock.acquire()
    cancel = threading.Event()
    started = threading.Event()
    outcomes = []

    def wait():
        started.set()
        try:
            acquire_cancellable(lock, should_cancel=cancel.is_set)
        except OperationCancelled:
            outcomes.append("cancelled")

    worker = threading.Thread(target=wait)
    worker.start()
    assert started.wait(1)
    cancel.set()
    worker.join(1)
    assert outcomes == ["cancelled"] and not worker.is_alive()
    assert lock.locked()
    lock.release()


def test_lock_wait_deadline_and_metrics():
    lock = threading.Lock()
    lock.acquire()
    timings = TurnMetrics()
    try:
        with bind_metrics(timings), pytest.raises(OperationTimeoutError):
            acquire_cancellable(lock, deadline=time.monotonic() + 0.02, phase_name="model_wait")
        assert "model_wait" in timings.phases
        assert lock.locked()
    finally:
        lock.release()


def test_nested_control_preserves_the_outer_deadline_and_cancellation():
    with bind_control(lambda: True), bind_control(None), pytest.raises(OperationCancelled):
        check_control()
    with (
        bind_control(None, time.monotonic() - 1),
        bind_control(None),
        pytest.raises(OperationTimeoutError),
    ):
        check_control()
    check_control()


def test_lock_is_released_on_failure_inside_context():
    lock = threading.Lock()
    with pytest.raises(ValueError), cancellable_lock(lock):
        raise ValueError("local failure")
    assert not lock.locked()


def test_cancellation_after_last_native_token_closes_generator_and_lock():
    lock = threading.Lock()
    lock.acquire()
    cancel = threading.Event()
    closed = []

    def native():
        try:
            cancel.set()
            yield "must not be published"
        finally:
            closed.append(True)

    stream = LockedIterator(native(), lock, should_cancel=cancel.is_set)
    with pytest.raises(OperationCancelled):
        next(stream)
    assert closed and not lock.locked()


def test_close_failure_still_releases_lock():
    lock = threading.Lock()
    lock.acquire()

    class Native:
        def __iter__(self):
            return self

        def __next__(self):
            return "token"

        def close(self):
            raise ValueError("close failed")

    stream = LockedIterator(Native(), lock)
    with pytest.raises(ValueError):
        stream.close()
    assert not lock.locked()


def test_common_responder_binds_cancellation_for_deep_helpers():
    @propagate_control
    def respond(prompt_dict, should_cancel=None):
        check_control()
        pytest.fail("cancelled responder ran")

    with pytest.raises(OperationCancelled):
        respond({}, should_cancel=lambda: True)


def test_engine_cancel_before_quick_reply_or_heavy_resources(monkeypatch):
    import ai.engine as engine

    monkeypatch.setattr(engine, "quick_response", lambda *a, **k: pytest.fail("continued"))
    with pytest.raises(OperationCancelled):
        engine.gerar_resposta({"pergunta": "quem é voce?"}, should_cancel=lambda: True)


def test_timings_contain_only_numbers_and_known_labels():
    timings = TurnMetrics()
    timings.first_token()
    timings.finish()
    assert set(timings.public_dict()) == {
        "phases_ms",
        "first_token_ms",
        "first_visible_token_ms",
        "total_ms",
        "model_state",
    }
    assert timings.public_dict()["model_state"] == "not_used"


@pytest.mark.parametrize(
    "text,seconds", [("Explique energia solar", 120), ("TAREFA: gere um relatório", 3600)]
)
def test_direct_responder_has_a_proportional_deadline(monkeypatch, text, seconds):
    import core.operation_control as control

    clock = [100.0]
    monkeypatch.setattr(control, "monotonic", lambda: clock[0])

    @propagate_control
    def respond(prompt_dict, should_cancel=None):
        clock[0] += seconds - 1
        check_control()
        clock[0] += 2
        check_control()
        pytest.fail("deadline not enforced")

    with pytest.raises(OperationTimeoutError):
        respond({"pergunta": text})


def test_direct_image_responder_keeps_outer_deadline(monkeypatch):
    import core.operation_control as control

    clock = [100.0]
    monkeypatch.setattr(control, "monotonic", lambda: clock[0])

    @propagate_control
    def respond(caminho_imagem, pergunta, should_cancel=None):
        clock[0] += 2
        check_control()

    with bind_control(None, 101), pytest.raises(OperationTimeoutError):
        respond("image.png", "Analise a imagem")
