from __future__ import annotations

import pytest
import yaml
from pathlib import Path

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
    (manifests / "wiki.yaml").write_text(yaml.dump({
        "name": "mock-wikipedia",
        "capability_tags": ["wikipedia"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "wikipedia:read",
        "priority": 10,
    }))
    return manifests


@pytest.fixture
def orchestrator(manifests_dir, tmp_path):
    registry = ToolRegistry()
    registry.load_manifests(manifests_dir)
    auditor = AuditLog(tmp_path / "audit.jsonl")
    return Orchestrator.create(registry, auditor=auditor)


@pytest.mark.asyncio
async def test_sub_task_execution(orchestrator):
    sub_task = SubTask(
        task_id="sub-1",
        steps=[Step(id="sub-step-1", capability="weather", input={"location": "NYC"})],
        allowed_scopes=["weather:read"],
    )
    results = await orchestrator.run_sub_task(sub_task, PermissionToken(task_id="parent", granted_scopes=["weather:read"]))
    assert "sub-step-1" in results
    assert results["sub-step-1"]["success"] is True


@pytest.mark.asyncio
async def test_sub_task_permission_isolation(orchestrator):
    sub_task = SubTask(
        task_id="sub-2",
        steps=[Step(id="sub-step-1", capability="weather", input={})],
        allowed_scopes=[],
    )
    results = await orchestrator.run_sub_task(sub_task, PermissionToken(task_id="parent", granted_scopes=["weather:read"]))
    assert results["sub-step-1"]["success"] is False


@pytest.mark.asyncio
async def test_parent_step_with_sub_task(orchestrator):
    task = Task(
        task_id="parent-1",
        steps=[
            Step(
                id="parent-step-1",
                capability="weather",
                input={},
                sub_task=SubTask(
                    task_id="child-1",
                    steps=[Step(id="child-step-1", capability="weather", input={"location": "NYC"})],
                    allowed_scopes=["weather:read"],
                ),
            ),
        ],
    )
    result = await orchestrator.run_task(task)
    assert result["results"]["parent-step-1"]["success"] is True
    assert "sub_task_id" in result["results"]["parent-step-1"]["output"]
    assert result["results"]["parent-step-1"]["output"]["sub_task_id"] == "child-1"


@pytest.mark.asyncio
async def test_nested_sub_tasks(orchestrator):
    task = Task(
        task_id="root",
        steps=[
            Step(
                id="step-1",
                capability="weather",
                input={},
                sub_task=SubTask(
                    task_id="level-1",
                    steps=[
                        Step(
                            id="level-1-step",
                            capability="weather",
                            input={},
                            sub_task=SubTask(
                                task_id="level-2",
                                steps=[Step(id="level-2-step", capability="weather", input={})],
                                allowed_scopes=["weather:read"],
                            ),
                        ),
                    ],
                    allowed_scopes=["weather:read"],
                ),
            ),
        ],
    )
    result = await orchestrator.run_task(task)
    assert result["results"]["step-1"]["success"] is True
    level1_output = result["results"]["step-1"]["output"]["results"]
    assert level1_output["level-1-step"]["success"] is True
