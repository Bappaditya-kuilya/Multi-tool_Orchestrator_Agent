"""DistributedExecutor round-trip: two workers, one task_id, isolated replies.

Run from the repo root:  .venv/bin/python examples/distributed-demo.py
"""

from __future__ import annotations

import asyncio
import json

from src.message_queue import DistributedExecutor, Message, MessageQueue


async def main() -> None:
    queue = MessageQueue()
    executor = DistributedExecutor(queue)

    async def calculator_worker(msg: Message) -> dict | None:
        # echo the request input so the reply is distinguishable
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"worker": "calculator", "echo": msg.payload["input"]["value"]},
        )
        await queue.publish(reply)
        return None

    async def weather_worker(msg: Message) -> dict | None:
        reply = Message(
            topic=msg.reply_to,
            correlation_id=msg.message_id,
            payload={"worker": "weather", "echo": msg.payload["input"]["value"]},
        )
        await queue.publish(reply)
        return None

    queue.subscribe("task.calculator", calculator_worker)
    queue.subscribe("task.weather", weather_worker)

    # Same task_id, two different workers: each submit_and_wait must get its
    # OWN reply (per-request reply topics + correlation_id), never the other's.
    calc = asyncio.create_task(
        executor.submit_and_wait("shared-task", "calculator", {"value": 1}, timeout=5.0)
    )
    weather = asyncio.create_task(
        executor.submit_and_wait("shared-task", "weather", {"value": 2}, timeout=5.0)
    )

    await asyncio.sleep(0.05)
    await queue.process("task.calculator")
    await queue.process("task.weather")

    r_calc, r_weather = await asyncio.gather(calc, weather)

    # Reply isolation proof: each result echoes only its own worker's payload
    assert r_calc == {"worker": "calculator", "echo": 1}, f"cross-delivery: {r_calc}"
    assert r_weather == {"worker": "weather", "echo": 2}, f"cross-delivery: {r_weather}"

    print("task_id: shared-task (two workers, same id)")
    print(f"  calculator -> {json.dumps(r_calc)}")
    print(f"  weather    -> {json.dumps(r_weather)}")
    print("reply isolation: OK (no cross-delivery between workers)")
    print(f"remaining queued replies: calculator={queue.pending_count('task.calculator')}, weather={queue.pending_count('task.weather')}")


if __name__ == "__main__":
    asyncio.run(main())