from __future__ import annotations

import pytest
import yaml

from src.models import Task, Step, SubTask, PermissionToken
from src.registry import ToolRegistry
from src.router import Router
from src.permission import PermissionScoper
from src.executor import Executor
from src.auditor import AuditLog
from src.orchestrator import Orchestrator


@pytest.fixture
def manifests_dir(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "weather.yaml").write_text(yaml.dump({
        "name": "mock-weather",
        "capability_tags": ["weather"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "weather:read",
        "priority": 10,
    }))
    return manifests


@pytest.fixture
def orchestrator(manifests_dir, tmp_path):
    registry = ToolRegistry()
    registry.load_manifests(manifests_dir)
    return Orchestrator.create(registry, auditor=AuditLog(tmp_path / "audit.jsonl"))


@pytest.mark.asyncio
async def test_empty_sub_task_steps_fail(orchestrator):
    task = Task(
        task_id="parent",
        steps=[
            Step(
                id="step-1",
                capability="weather",
                input={},
                sub_task=SubTask(task_id="child", steps=[], allowed_scopes=["weather:read"]),
            ),
        ],
    )
    result = await orchestrator.run_task(task)
    assert result["results"]["step-1"]["success"] is False
    assert result["results"]["step-1"]["error"] == "Sub-task has no steps"


@pytest.mark.asyncio
async def test_nested_sub_tasks_beyond_depth_limit_fail_cleanly(orchestrator):
    leaf = SubTask(
        task_id="level-55",
        steps=[Step(id="s-55", capability="weather", input={})],
        allowed_scopes=["weather:read"],
    )
    for i in range(54, 0, -1):
        leaf = SubTask(
            task_id=f"level-{i}",
            steps=[Step(id=f"s-{i}", capability="weather", input={}, sub_task=leaf)],
            allowed_scopes=["weather:read"],
        )
    task = Task(
        task_id="root",
        steps=[Step(id="root-step", capability="weather", input={}, sub_task=leaf)],
    )
    result = await orchestrator.run_task(task)
    assert result["results"]["root-step"]["success"] is False
    assert "depth" in result["results"]["root-step"]["error"].lower()


@pytest.mark.asyncio
async def test_sub_task_without_handler_fails_explicitly(manifests_dir, tmp_path):
    registry = ToolRegistry()
    registry.load_manifests(manifests_dir)
    router = Router(registry)
    scoper = PermissionScoper(registry, router)
    auditor = AuditLog(tmp_path / "audit.jsonl")
    executor = Executor(registry, router, scoper, auditor, sub_task_handler=None)
    steps = [
        Step(
            id="step-1",
            capability="weather",
            input={},
            sub_task=SubTask(
                task_id="child",
                steps=[Step(id="child-step", capability="weather", input={})],
                allowed_scopes=["weather:read"],
            ),
        ),
    ]
    results = await executor.run(steps, PermissionToken(task_id="t", granted_scopes=["weather:read"]))
    assert results["step-1"].success is False
    assert results["step-1"].error == "No sub-task handler"