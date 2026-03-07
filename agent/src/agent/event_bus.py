from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

MAX_SSE_CONNECTIONS = 5
MAX_JOB_SSE_CONNECTIONS = 10
SSE_TIMEOUT_SECONDS = 3600  # 1 hour


class Event(BaseModel):
    type: str
    message: str
    timestamp: str
    job_id: str | None = None


class EventBus:
    def __init__(self, max_history: int = 200) -> None:
        self._subscribers: list[asyncio.Queue[Event]] = []
        self._job_subscribers: list[asyncio.Queue[Event]] = []
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

    def check_job_connection_limit(self) -> None:
        """Raise ConnectionError if the max job SSE connection limit is reached."""
        if len(self._job_subscribers) >= MAX_JOB_SSE_CONNECTIONS:
            logger.warning("Job SSE connection limit reached (%d)", MAX_JOB_SSE_CONNECTIONS)
            raise ConnectionError(f"Maximum job SSE connections ({MAX_JOB_SSE_CONNECTIONS}) exceeded")

    def emit(self, event_type: str, message: str, *, job_id: str | None = None) -> None:
        logger.info("[%s] %s", event_type, message)
        event = Event(
            type=event_type,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            job_id=job_id,
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

    async def subscribe_job(self, job_id: str):
        """Subscribe to events for a specific job only."""
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        self._job_subscribers.append(q)

        # Replay matching events from history
        for event in self._history:
            if event.job_id == job_id:
                await q.put(event)

        try:
            deadline = asyncio.get_event_loop().time() + SSE_TIMEOUT_SECONDS
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    logger.info("Job SSE connection for %s timed out after %ds", job_id, SSE_TIMEOUT_SECONDS)
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=remaining)
                    if event.job_id == job_id:
                        yield event
                except asyncio.TimeoutError:
                    logger.info("Job SSE connection for %s timed out after %ds", job_id, SSE_TIMEOUT_SECONDS)
                    break
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)
            if q in self._job_subscribers:
                self._job_subscribers.remove(q)
