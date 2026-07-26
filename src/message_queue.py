from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class Message:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    topic: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    sender: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat() + "Z")
    reply_to: str | None = None


MessageHandler = Callable[[Message], Awaitable[dict[str, Any] | None]]


class MessageQueue:
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

    async def publish(self, message: Message) -> str:
        self.create_topic(message.topic)
        self._history.append(message)
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

        handlers = self._handlers.get(topic, [])
        result = None
        for handler in handlers:
            try:
                result = await handler(message)
            except Exception as e:
                logger.error("Handler failed for message %s: %s", message.message_id, e)

        return result

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

    async def submit_task(self, task_id: str, tool_name: str, input_data: dict[str, Any]) -> str:
        message = Message(
            topic=f"task.{tool_name}",
            payload={"task_id": task_id, "input": input_data},
            sender="orchestrator",
        )
        return await self.queue.publish(message)

    async def submit_and_wait(self, task_id: str, tool_name: str, input_data: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        message = Message(
            topic=f"task.{tool_name}",
            payload={"task_id": task_id, "input": input_data},
            sender="orchestrator",
            reply_to=f"reply.{task_id}",
        )

        reply_queue = asyncio.Queue()
        self.queue.create_topic(message.reply_to)

        async def reply_handler(msg: Message) -> None:
            await reply_queue.put(msg)

        self.queue.subscribe(message.reply_to, reply_handler)
        await self.queue.publish(message)

        try:
            reply = await asyncio.wait_for(reply_queue.get(), timeout=timeout)
            return reply.payload
        except asyncio.TimeoutError:
            return {"error": "Timeout waiting for reply"}

    def get_results(self, task_id: str) -> dict[str, Any] | None:
        return self._results.get(task_id)
