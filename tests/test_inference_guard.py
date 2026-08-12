"""Tests for native model concurrency guards."""

from threading import Lock

import pytest

from core.inference_guard import LockedIterator


class TestLockedIterator:
    def test_releases_lock_after_stream_finishes(self):
        lock = Lock()
        lock.acquire()

        stream = LockedIterator(iter(("a", "b")), lock)

        assert list(stream) == ["a", "b"]
        assert lock.acquire(blocking=False)
        lock.release()

    def test_releases_lock_when_stream_raises(self):
        lock = Lock()
        lock.acquire()

        def failing_stream():
            yield "primeiro"
            raise ValueError("falha")

        stream = LockedIterator(failing_stream(), lock)
        assert next(stream) == "primeiro"
        with pytest.raises(ValueError, match="falha"):
            next(stream)

        assert lock.acquire(blocking=False)
        lock.release()

    def test_close_releases_lock(self):
        lock = Lock()
        lock.acquire()
        stream = LockedIterator(iter(("a", "b")), lock)

        stream.close()

        assert lock.acquire(blocking=False)
        lock.release()
