from __future__ import annotations

import pytest
import asyncio

from src.models import Task, Step, ToolResult, PermissionToken
from src.registry import ToolRegistry
from src.router import Router
from src.permission import PermissionScoper
from src.executor import Executor, ParallelExecutor
from src.auditor import AuditLog
from src.tools import create_tool


@pytest.fixture
def registry(tmp_path):
    reg = ToolRegistry()
    # Create mock manifests
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    for name in ["mock-weather", "mock-calculator", "mock-wikipedia", "mock-github-search"]:
        cap = name.replace('mock-', '')
        scope = "calculator:eval" if cap == "calculator" else f"{cap}:read"
        (manifests_dir / f"{name}.yaml").write_text(f"""
name: "{name}"
capability_tags: ["{cap}"]
input_schema: {{"type": "object", "properties": {{}}}}
output_schema: {{"type": "object", "properties": {{}}}}
required_scope: "{scope}"
priority: 10
""")
    reg.load_manifests(manifests_dir)
    return reg


@pytest.fixture
def executor(registry, tmp_path):
    router = Router(registry)
    scoper = PermissionScoper(registry, router)
    auditor = AuditLog(str(tmp_path / "test_audit.jsonl"))
    return Executor(registry, router, scoper, auditor)

@pytest.mark.asyncio
async def test_sequential_execution(executor):
    steps = [
        Step(id="calc-1", capability="calculator", input={"expression": "2 + 2"}),
        Step(id="weather-1", capability="weather", input={"location": "London"}),
    ]
    token = PermissionToken(task_id="test", granted_scopes=["calculator:eval", "weather:read"])
    results = await executor.run(steps, token)
    assert "calc-1" in results
    assert "weather-1" in results
    assert results["calc-1"].success
    assert results["weather-1"].success


@pytest.mark.asyncio
async def test_dependency_order(executor):
    steps = [
        Step(id="step-2", capability="weather", input={"location": "London"}, dependencies=["step-1"]),
        Step(id="step-1", capability="calculator", input={"expression": "1 + 1"}),
    ]
    token = PermissionToken(task_id="test", granted_scopes=["calculator:eval", "weather:read"])
    results = await executor.run(steps, token)
    assert results["step-1"].success
    assert results["step-2"].success


@pytest.mark.asyncio
async def test_permission_denied(executor):
    steps = [Step(id="calc-1", capability="calculator", input={"expression": "2 + 2"})]
    token = PermissionToken(task_id="test", granted_scopes=[])
    results = await executor.run(steps, token)
    assert not results["calc-1"].success
    assert "not granted" in results["calc-1"].error


@pytest.mark.asyncio
async def test_duplicate_step_ids_rejected(executor):
    steps = [
        Step(id="dup", capability="calculator", input={"expression": "2 + 2"}),
        Step(id="dup", capability="weather", input={"location": "London"}),
    ]
    token = PermissionToken(task_id="test", granted_scopes=["calculator:eval", "weather:read"])
    with pytest.raises(ValueError, match="Duplicate step id: dup"):
        await executor.run(steps, token)


@pytest.mark.asyncio
async def test_duplicate_step_ids_rejected_parallel(registry, tmp_path):
    router = Router(registry)
    scoper = PermissionScoper(registry, router)
    auditor = AuditLog(str(tmp_path / "test_audit.jsonl"))
    executor = ParallelExecutor(registry, router, scoper, auditor)
    steps = [
        Step(id="dup", capability="calculator", input={"expression": "2 + 2"}),
        Step(id="dup", capability="weather", input={"location": "London"}),
    ]
    token = PermissionToken(task_id="test", granted_scopes=["calculator:eval", "weather:read"])
    with pytest.raises(ValueError, match="Duplicate step id: dup"):
        await executor.run(steps, token)