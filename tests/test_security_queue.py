from __future__ import annotations

import asyncio

import pytest

from src.message_queue import Message, MessageQueue, DistributedExecutor


@pytest.fixture
def queue():
    return MessageQueue()


@pytest.fixture
def executor(queue):
    return DistributedExecutor(queue)


def _total_handlers(queue: MessageQueue) -> int:
    return sum(len(handlers) for handlers in queue._handlers.values())


@pytest.mark.asyncio
async def test_forged_reply_on_reply_topic_is_rejected(queue, executor):
    async def worker(msg: Message) -> dict | None:
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"status": "ok", "value": 42},
        )
        await queue.publish(reply)
        return None

    queue.subscribe("task.worker", worker)

    request_task = asyncio.create_task(
        executor.submit_and_wait("t1", "worker", {"x": 1}, timeout=5.0)
    )
    await asyncio.sleep(0.05)

    request = queue.get_history(topic="task.worker")[-1]
    forged = Message(
        topic=request.reply_to,
        correlation_id="forged-" + request.message_id,
        payload={"status": "hacked", "flag": True},
    )
    await queue.publish(forged)
    await queue.publish(Message(topic="reply.t1", correlation_id="x", payload={"status": "hacked"}))
    await queue.process("task.worker")

    result = await request_task
    assert result == {"status": "ok", "value": 42}
    assert result.get("status") != "hacked"


@pytest.mark.asyncio
async def test_concurrent_same_task_id_no_cross_delivery(queue, executor):
    async def worker(msg: Message) -> dict | None:
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"echo": msg.message_id, "task_id": msg.payload["task_id"]},
        )
        await queue.publish(reply)
        return None

    queue.subscribe("task.worker", worker)

    calls = [
        asyncio.create_task(executor.submit_and_wait("same", "worker", {}, timeout=5.0))
        for _ in range(2)
    ]
    await asyncio.sleep(0.05)
    requests = queue.get_history(topic="task.worker")
    await queue.process("task.worker")
    await queue.process("task.worker")

    results = await asyncio.gather(*calls)

    assert len(results) == 2
    assert all(r["task_id"] == "same" for r in results)
    assert {r["echo"] for r in results} == {req.message_id for req in requests}


@pytest.mark.asyncio
async def test_no_handler_leak_after_reply(queue, executor):
    baseline = _total_handlers(queue)

    async def worker(msg: Message) -> dict | None:
        reply = Message(topic=msg.reply_to, correlation_id=msg.message_id, payload={"status": "done"})
        await queue.publish(reply)
        return None

    queue.subscribe("task.worker", worker)

    task = asyncio.create_task(executor.submit_and_wait("t2", "worker", {}, timeout=5.0))
    await asyncio.sleep(0.05)
    await queue.process("task.worker")
    result = await task
    assert result == {"status": "done"}
    assert _total_handlers(queue) == baseline + 1

    result = await executor.submit_and_wait("t3", "worker", {}, timeout=0.2)
    assert result == {"error": "Timeout waiting for reply"}
    assert _total_handlers(queue) == baseline + 1


@pytest.mark.asyncio
async def test_get_results_returns_stored_results(queue, executor):
    async def worker(msg: Message) -> dict | None:
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"status": "ok", "value": 42},
        )
        await queue.publish(reply)
        return None

    queue.subscribe("task.worker", worker)

    task = asyncio.create_task(executor.submit_and_wait("t4", "worker", {"x": 1}, timeout=5.0))
    await asyncio.sleep(0.05)
    await queue.process("task.worker")
    result = await task

    assert result == {"status": "ok", "value": 42}
    assert executor.get_results("t4") == {"status": "ok", "value": 42}
