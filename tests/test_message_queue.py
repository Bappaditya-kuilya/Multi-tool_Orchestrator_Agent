from __future__ import annotations

import pytest
import asyncio
from datetime import datetime, timedelta

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


@pytest.mark.asyncio
async def test_submit_and_wait_round_trip(queue):
    executor = DistributedExecutor(queue)

    async def worker(msg: Message) -> None:
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"status": "done", "echo": msg.payload["input"]["value"]},
        )
        await queue.publish(reply)

    queue.subscribe("task.worker", worker)

    task = asyncio.create_task(
        executor.submit_and_wait("t1", "worker", {"value": 7}, timeout=5.0)
    )
    await asyncio.sleep(0.05)
    await queue.process("task.worker")
    result = await task

    assert result == {"status": "done", "echo": 7}


@pytest.mark.asyncio
async def test_same_task_id_sequential_gets_only_own_reply(queue):
    executor = DistributedExecutor(queue)

    async def worker(msg: Message) -> None:
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"echo": msg.payload["input"]["value"]},
        )
        await queue.publish(reply)

    queue.subscribe("task.worker", worker)

    first = asyncio.create_task(
        executor.submit_and_wait("same", "worker", {"value": 1}, timeout=5.0)
    )
    await asyncio.sleep(0.05)
    await queue.process("task.worker")
    r1 = await first

    second = asyncio.create_task(
        executor.submit_and_wait("same", "worker", {"value": 2}, timeout=5.0)
    )
    await asyncio.sleep(0.05)
    await queue.process("task.worker")
    r2 = await second

    assert r1 == {"echo": 1}
    assert r2 == {"echo": 2}
    assert executor.get_results("same") == {"echo": 2}


def test_get_results_unknown_task_is_none(queue):
    executor = DistributedExecutor(queue)
    assert executor.get_results("never-submitted") is None


@pytest.mark.asyncio
async def test_1000_submits_leave_no_stray_handlers(queue):
    executor = DistributedExecutor(queue)
    reply_topics = []

    async def worker(msg: Message) -> None:
        reply_topics.append(msg.reply_to)
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"status": "done"},
        )
        await queue.publish(reply)

    queue.subscribe("task.worker", worker)

    for i in range(1000):
        await executor.submit_task(f"t{i}", "worker", {"x": i})

    for _ in range(1000):
        await queue.process("task.worker", timeout=0.05)

    assert len(reply_topics) == 1000
    for topic in reply_topics:
        await queue.process(topic, timeout=0.05)

    for topic in reply_topics:
        assert len(queue._handlers[topic]) == 0
    assert sum(len(handlers) for handlers in queue._handlers.values()) == 1
    assert executor.get_results("t999") == {"status": "done"}


@pytest.mark.asyncio
async def test_history_capped_at_10000(queue):
    for i in range(10_001):
        await queue.publish(Message(topic="cap", payload={"i": i}))

    assert len(queue._history) == 10_000
    assert queue._history[0].payload == {"i": 1}
    assert queue._history[-1].payload == {"i": 10_000}


@pytest.mark.asyncio
async def test_message_timestamp_is_tz_aware_utc(queue):
    await queue.publish(Message(topic="ts", payload={}))
    msg = queue._history[0]
    ts = datetime.fromisoformat(msg.timestamp)
    assert ts.tzinfo is not None
    assert ts.utcoffset() == timedelta(0)
