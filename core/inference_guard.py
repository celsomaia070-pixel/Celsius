"""Concurrency helpers for native model inference streams."""

from __future__ import annotations

import contextlib
from collections.abc import Iterable, Iterator
from threading import Lock
from typing import Generic, TypeVar

from core.operation_control import check_control

T = TypeVar("T")


class LockedIterator(Iterator[T], Generic[T]):
    """Keep a lock held until an iterator finishes or is explicitly closed."""

    def __init__(self, iterable: Iterable[T], lock: Lock, *, should_cancel=None, deadline=None):
        self._lock = lock
        self._released = True
        self._iterator = iter(iterable)
        self._released = False
        self._should_cancel = should_cancel
        self._deadline = deadline

    def __iter__(self) -> LockedIterator[T]:
        return self

    def __next__(self) -> T:
        try:
            check_control(self._should_cancel, self._deadline)
            value = next(self._iterator)
            check_control(self._should_cancel, self._deadline)
            return value
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        try:
            close = getattr(self._iterator, "close", None)
            if close is not None:
                close()
        finally:
            self._release()

    def _release(self) -> None:
        if self._released:
            return
        self._released = True
        self._lock.release()

    def __del__(self) -> None:
        with contextlib.suppress(RuntimeError):
            self._release()
