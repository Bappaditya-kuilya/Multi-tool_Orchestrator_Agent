from __future__ import annotations

import pytest
import asyncio

from src.message_queue import Message, MessageQueue, DistributedExecutor


@pytest.fixture
def queue():
    return MessageQueue()


@pytest.mark.asyncio
async def test_publish_consume(queue):
    msg = Message(topic="test", payload={"key": "value"})
    await queue.publish(msg)
    received = await queue.consume("test")
    assert received is not None
    assert received.payload == {"key": "value"}


@pytest.mark.asyncio
async def test_subscribe_handler(queue):
    results = []

    async def handler(msg: Message) -> dict[str, Any]:
        results.append(msg.payload)
        return {"status": "ok"}

    queue.subscribe("test", handler)
    msg = Message(topic="test", payload={"data": 123})
    await queue.publish(msg)
    await queue.process("test")
    assert results == [{"data": 123}]


@pytest.mark.asyncio
async def test_message_history(queue):
    await queue.publish(Message(topic="a", payload={}))
    await queue.publish(Message(topic="b", payload={}))
    await queue.publish(Message(topic="a", payload={}))

    all_history = queue.get_history()
    assert len(all_history) == 3

    a_history = queue.get_history(topic="a")
    assert len(a_history) == 2


@pytest.mark.asyncio
async def test_pending_count(queue):
    assert queue.pending_count("test") == 0
    await queue.publish(Message(topic="test", payload={}))
    assert queue.pending_count("test") == 1
    await queue.consume("test")
    assert queue.pending_count("test") == 0


@pytest.mark.asyncio
async def test_consume_timeout(queue):
    result = await queue.consume("empty", timeout=0.05)
    assert result is None


@pytest.mark.asyncio
async def test_distributed_executor():
    queue = MessageQueue()
    executor = DistributedExecutor(queue)

    results = []

    async def worker(msg: Message) -> None:
        results.append(msg.payload)
        if msg.reply_to:
            reply = Message(topic=msg.reply_to, payload={"status": "done"})
            await queue.publish(reply)

    queue.subscribe("task.worker", worker)

    msg_id = await executor.submit_task("t1", "worker", {"x": 1})
    assert msg_id

    await asyncio.sleep(0.1)
    await queue.process("task.worker")
    assert len(results) == 1
    assert results[0]["input"] == {"x": 1}
