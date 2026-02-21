from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Event(BaseModel):
    type: str
    message: str
    timestamp: str


class EventBus:
    def __init__(self, max_history: int = 200) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._history: list[Event] = []
        self._max_history = max_history

    def emit(self, event_type: str, message: str) -> None:
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
            while True:
                event = await q.get()
                yield event
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)
