from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class Message:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    sender: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reply_to: str | None = None
    correlation_id: str | None = None


MessageHandler = Callable[[Message], Awaitable[dict[str, Any] | None]]


class MessageQueue:
    _HISTORY_CAP = 10_000

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Message]] = {}
        self._handlers: dict[str, list[MessageHandler]] = {}
        self._history: list[Message] = []

    def create_topic(self, topic: str) -> None:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue()
            self._handlers[topic] = []

    def subscribe(self, topic: str, handler: MessageHandler) -> None:
        self.create_topic(topic)
        self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: MessageHandler) -> None:
        handlers = self._handlers.get(topic)
        if handlers is not None and handler in handlers:
            handlers.remove(handler)

    async def publish(self, message: Message) -> str:
        self.create_topic(message.topic)
        self._history.append(message)
        if len(self._history) > self._HISTORY_CAP:
            # ponytail: ring buffer, swap to disk-backed if real traffic
            del self._history[: len(self._history) - self._HISTORY_CAP]
        await self._queues[message.topic].put(message)
        logger.debug("Published message %s to topic %s", message.message_id, message.topic)
        return message.message_id

    async def consume(self, topic: str, timeout: float = 1.0) -> Message | None:
        self.create_topic(topic)
        try:
            return await asyncio.wait_for(self._queues[topic].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def process(self, topic: str, timeout: float = 1.0) -> dict[str, Any] | None:
        message = await self.consume(topic, timeout)
        if message is None:
            return None

        result = None
        for handler in list(self._handlers.get(topic, [])):
            try:
                result = await handler(message)
            except Exception as e:
                logger.error("Handler failed for message %s: %s", message.message_id, e)

        return result

    def pop_buffered(self, topic: str) -> list[Message]:
        """Pop all messages buffered for a topic without running handlers.

        Buffered-reply read path: replies published before a consumer attached
        (or between polls) stay queued here until popped or consumed — the
        drain-vs-process invariant lives in the queue, so consumers never
        reach into topic internals (F-5).
        """
        messages = []
        while True:
            try:
                messages.append(self._queues[topic].get_nowait())
            except (KeyError, asyncio.QueueEmpty):
                return messages

    def get_history(self, topic: str | None = None) -> list[Message]:
        if topic:
            return [m for m in self._history if m.topic == topic]
        return list(self._history)

    def pending_count(self, topic: str) -> int:
        if topic in self._queues:
            return self._queues[topic].qsize()
        return 0


class DistributedExecutor:
    def __init__(self, queue: MessageQueue) -> None:
        self.queue = queue
        self._results: dict[str, dict[str, Any]] = {}

    def _new_request(self, task_id: str, tool_name: str, input_data: dict[str, Any]) -> Message:
        request_id = str(uuid.uuid4())
        return Message(
            message_id=request_id,
            topic=f"task.{tool_name}",
            payload={"task_id": task_id, "input": input_data},
            sender="orchestrator",
            # unique per-request reply topic: a task_id-based topic lets any
            # party knowing the task_id eavesdrop on worker replies (H-3)
            reply_to=f"reply.{request_id}",
        )

    async def submit_task(self, task_id: str, tool_name: str, input_data: dict[str, Any]) -> str:
        message = self._new_request(task_id, tool_name, input_data)
        reply_topic = message.reply_to
        self.queue.create_topic(reply_topic)

        async def store_reply(msg: Message) -> dict[str, Any] | None:
            if msg.correlation_id == message.message_id:
                self._results[task_id] = msg.payload
                self.queue.unsubscribe(reply_topic, store_reply)
            return None

        self.queue.subscribe(reply_topic, store_reply)
        return await self.queue.publish(message)

    async def submit_and_wait(
        self, task_id: str, tool_name: str, input_data: dict[str, Any], timeout: float = 30.0
    ) -> dict[str, Any]:
        message = self._new_request(task_id, tool_name, input_data)
        reply_topic = message.reply_to
        reply_queue: asyncio.Queue[Message] = asyncio.Queue()

        async def reply_handler(msg: Message) -> dict[str, Any] | None:
            # ponytail: in-process trust boundary, HMAC per-message auth only if workers leave the process
            if msg.correlation_id == message.message_id:
                reply_queue.put_nowait(msg)
            return None

        self.queue.create_topic(reply_topic)
        self.queue.subscribe(reply_topic, reply_handler)
        try:
            await self.queue.publish(message)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while True:
                # queue-owned buffer: replies delivered before subscribe (or
                # between polls) are popped here, not lost (F-5)
                for buffered in self.queue.pop_buffered(reply_topic):
                    if buffered.correlation_id == message.message_id:
                        reply_queue.put_nowait(buffered)
                try:
                    reply = reply_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                else:
                    self._results[task_id] = reply.payload
                    return reply.payload
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return {"error": "Timeout waiting for reply"}
                try:
                    reply = await asyncio.wait_for(reply_queue.get(), timeout=min(remaining, 0.1))
                except asyncio.TimeoutError:
                    continue
                self._results[task_id] = reply.payload
                return reply.payload
        finally:
            self.queue.unsubscribe(reply_topic, reply_handler)

    def get_results(self, task_id: str) -> dict[str, Any] | None:
        """Latest stored reply for a completed task; None for an unknown task (nothing stored yet)."""
        return self._results.get(task_id)
