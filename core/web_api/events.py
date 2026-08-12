"""Thread-safe event distribution for web clients."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any


class EventHub:
    """Publish Celsius state changes to connected async clients from any thread."""

    def __init__(self, *, queue_size: int = 100):
        self.queue_size = max(1, queue_size)
        self._lock = threading.Lock()
        self._next_subscriber_id = 0
        self._subscribers: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = {}

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        with self._lock:
            subscriber_id = self._next_subscriber_id
            self._next_subscriber_id += 1
            self._subscribers[subscriber_id] = (loop, queue)
        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.pop(subscriber_id, None)

    def publish(self, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "id": uuid.uuid4().hex,
            "type": event_type,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
        }
        with self._lock:
            subscribers = list(self._subscribers.values())
        for loop, queue in subscribers:
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._enqueue_latest, queue, event)
        return event

    @staticmethod
    def _enqueue_latest(queue: asyncio.Queue, event: dict[str, Any]) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(event)


_event_hub: EventHub | None = None
_event_hub_lock = threading.Lock()


def get_event_hub() -> EventHub:
    global _event_hub
    if _event_hub is None:
        with _event_hub_lock:
            if _event_hub is None:
                _event_hub = EventHub()
    return _event_hub
