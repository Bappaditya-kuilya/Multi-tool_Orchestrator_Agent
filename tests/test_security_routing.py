from __future__ import annotations

import pytest

from src.executor import Executor, ParallelExecutor
from src.models import PermissionToken, Step


def _token() -> PermissionToken:
    return PermissionToken(task_id="routing-test", granted_scopes=["calculator:eval", "weather:read"])


@pytest.mark.asyncio
async def test_executor_unknown_capability_returns_failed_result(executor):
    steps = [
        Step(id="ok-1", capability="calculator", input={"expression": "1 + 1"}),
        Step(id="bad-1", capability="no-such-capability", input={}),
    ]
    results = await executor.run(steps, _token())
    assert results["ok-1"].success
    assert not results["bad-1"].success
    assert results["bad-1"].error == "No tool for capability: no-such-capability"


@pytest.mark.asyncio
async def test_parallel_executor_unknown_capability_returns_failed_result(registry, router, scoper, auditor):
    executor = ParallelExecutor(registry, router, scoper, auditor)
    steps = [
        Step(id="ok-1", capability="calculator", input={"expression": "1 + 1"}),
        Step(id="bad-1", capability="no-such-capability", input={}),
    ]
    results = await executor.run(steps, _token())
    assert results["ok-1"].success
    assert not results["bad-1"].success
    assert results["bad-1"].error == "No tool for capability: no-such-capability"
