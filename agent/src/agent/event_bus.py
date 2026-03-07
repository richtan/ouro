from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

MAX_SSE_CONNECTIONS = 5
SSE_TIMEOUT_SECONDS = 3600  # 1 hour


class Event(BaseModel):
    type: str
    message: str
    timestamp: str


class EventBus:
    def __init__(self, max_history: int = 200) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._history: list[Event] = []
        self._max_history = max_history

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def check_connection_limit(self) -> None:
        """Raise ConnectionError if the max SSE connection limit is reached."""
        if len(self._subscribers) >= MAX_SSE_CONNECTIONS:
            logger.warning("SSE connection limit reached (%d)", MAX_SSE_CONNECTIONS)
            raise ConnectionError(f"Maximum SSE connections ({MAX_SSE_CONNECTIONS}) exceeded")

    def emit(self, event_type: str, message: str) -> None:
        logger.info("[%s] %s", event_type, message)
        event = Event(
            type=event_type,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

    async def subscribe(self):
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)

        for event in self._history[-50:]:
            await q.put(event)

        try:
            deadline = asyncio.get_event_loop().time() + SSE_TIMEOUT_SECONDS
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.info("SSE connection timed out after %ds", SSE_TIMEOUT_SECONDS)
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=remaining)
                    yield event
                except asyncio.TimeoutError:
                    logger.info("SSE connection timed out after %ds", SSE_TIMEOUT_SECONDS)
                    break
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)
