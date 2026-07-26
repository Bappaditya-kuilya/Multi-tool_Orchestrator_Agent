from __future__ import annotations

import pytest
import asyncio
import json
from pathlib import Path

from src.models import Task, Step
from src.orchestrator import Orchestrator


@pytest.fixture
def demo_task(tmp_path):
    task_data = {
        "task_id": "demo-1",
        "steps": [
            {"id": "calc-1", "capability": "calculator", "input": {"expression": "2 + 2 * 3"}},
            {"id": "weather-1", "capability": "weather", "input": {"location": "London"}},
            {"id": "wiki-1", "capability": "wikipedia", "input": {"query": "Python (programming language)"}},
            {"id": "gh-1", "capability": "github-search", "input": {"query": "pydantic"}},
        ],
    }
    task_file = tmp_path / "demo-task.json"
    task_file.write_text(json.dumps(task_data))
    return task_file


@pytest.mark.asyncio
async def test_full_demo_task(demo_task, tmp_path):
    orch, task = Orchestrator.from_task_file(demo_task, "manifests", tmp_path / "audit.jsonl")
    result = await orch.run_task(task)

    assert result["task_id"] == "demo-1"
    assert "calc-1" in result["results"]
    assert "weather-1" in result["results"]
    assert "wiki-1" in result["results"]
    assert "gh-1" in result["results"]

    for step_id, step_result in result["results"].items():
        assert step_result["success"], f"Step {step_id} failed: {step_result.get('error')}"

    # Verify audit log was written
    audit_entries = []
    with open(tmp_path / "audit.jsonl") as f:
        for line in f:
            audit_entries.append(json.loads(line))
    assert len(audit_entries) == 4


@pytest.mark.asyncio
async def test_conflict_resolution(tmp_path):
    # Create manifests with conflict
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "calc-high.yaml").write_text("""
name: "calc-high"
capability_tags: ["calculator"]
input_schema: {"type": "object", "properties": {"expression": {"type": "string"}}}
output_schema: {"type": "object", "properties": {"result": {"type": "number"}}}
required_scope: "calculator:eval"
priority: 20
""")
    (manifests_dir / "calc-low.yaml").write_text("""
name: "calc-low"
capability_tags: ["calculator"]
input_schema: {"type": "object", "properties": {"expression": {"type": "string"}}}
output_schema: {"type": "object", "properties": {"result": {"type": "number"}}}
required_scope: "calculator:eval"
priority: 5
""")

    # Use the classmethod to create orchestrator
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "task_id": "conflict-test",
        "steps": [{"id": "calc-1", "capability": "calculator", "input": {"expression": "2+2"}}]
    }))
    
    orch, task = Orchestrator.from_task_file(task_file, manifests_dir, tmp_path / "audit.jsonl")
    result = await orch.run_task(task)

    assert result["results"]["calc-1"]["success"]
    # Should use the higher priority tool (calc-high)
    assert result["results"]["calc-1"]["output"]["result"] == 4