from __future__ import annotations

import time
import pytest

from src.models import Step, PermissionToken
from src.executor import Executor, ParallelExecutor
from src.auditor import AuditLog


@pytest.fixture
def sequential_executor(registry, router, scoper, audit_path):
    return Executor(registry, router, scoper, AuditLog(audit_path))


@pytest.fixture
def parallel_executor(registry, router, scoper, audit_path):
    return ParallelExecutor(registry, router, scoper, AuditLog(audit_path))


def _signature(results):
    return {
        step_id: (r.success, r.output, r.error, r.tool_name)
        for step_id, r in results.items()
    }


@pytest.mark.asyncio
async def test_parallel_speedup(sequential_executor, parallel_executor):
    steps = [
        Step(id="weather-1", capability="weather", input={"location": "London"}),
        Step(id="wiki-1", capability="wikipedia", input={"query": "Python"}),
        Step(id="calc-1", capability="calculator", input={"expression": "2+2"}),
        Step(id="gh-1", capability="github-search", input={"query": "pydantic"}),
    ]
    token = PermissionToken(task_id="bench", granted_scopes=["weather:read", "wikipedia:read", "calculator:eval", "github:search"])

    start_seq = time.perf_counter()
    seq_results = await sequential_executor.run(steps, token)
    seq_time = time.perf_counter() - start_seq

    start_par = time.perf_counter()
    par_results = await parallel_executor.run(steps, token)
    par_time = time.perf_counter() - start_par

    assert all(r.success for r in seq_results.values()), "Sequential results should all succeed"
    assert all(r.success for r in par_results.values()), "Parallel results should all succeed"

    assert _signature(seq_results) == _signature(par_results), \
        "Sequential and parallel executors should produce identical results"

    speedup = seq_time / par_time
    assert speedup > 1.2, f"Expected speedup > 1.2x, got {speedup:.2f}x (seq={seq_time:.2f}s, par={par_time:.2f}s)"


@pytest.mark.asyncio
async def test_parallel_dependency_respected(parallel_executor):
    steps = [
        Step(id="step-2", capability="weather", input={"location": "London"}, dependencies=["step-1"]),
        Step(id="step-1", capability="calculator", input={"expression": "1+1"}),
    ]
    token = PermissionToken(task_id="dep-test", granted_scopes=["weather:read", "calculator:eval"])
    results = await parallel_executor.run(steps, token)

    assert results["step-1"].success
    assert results["step-2"].success


@pytest.mark.asyncio
async def test_parallel_permission_denied(parallel_executor):
    steps = [
        Step(id="weather-1", capability="weather", input={"location": "London"}),
    ]
    token = PermissionToken(task_id="perm-test", granted_scopes=[])
    results = await parallel_executor.run(steps, token)

    assert not results["weather-1"].success
    assert "not granted" in results["weather-1"].error