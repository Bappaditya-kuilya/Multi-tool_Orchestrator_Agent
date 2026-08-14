from __future__ import annotations

import pytest
import asyncio
import json
from pathlib import Path

from src.orchestrator import Orchestrator
from src.executor import Executor, ParallelExecutor
from src.auditor import AuditLog
from conftest import write_manifest


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
async def test_full_demo_task(demo_task, temp_manifests_dir, sample_manifests, audit_path):
    orch, task = Orchestrator.from_task_file(demo_task, temp_manifests_dir, audit_path)
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
    with open(audit_path) as f:
        for line in f:
            audit_entries.append(json.loads(line))
    assert len(audit_entries) == 4


@pytest.mark.asyncio
async def test_priority_ordering(tmp_path, audit_path):
    # Two manifests for the same capability; higher priority must win
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    write_manifest(manifests_dir, "mock-calculator-advanced", {
        "capability_tags": ["calculator"],
        "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "number"}}},
        "required_scope": "calculator:eval",
        "priority": 20,
    })
    write_manifest(manifests_dir, "mock-calculator", {
        "capability_tags": ["calculator"],
        "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "number"}}},
        "required_scope": "calculator:eval",
        "priority": 5,
    })

    # Use the classmethod to create orchestrator
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({
        "task_id": "priority-test",
        "steps": [{"id": "calc-1", "capability": "calculator", "input": {"expression": "2+2"}}]
    }))

    orch, task = Orchestrator.from_task_file(task_file, manifests_dir, audit_path)
    result = await orch.run_task(task)

    assert result["results"]["calc-1"]["success"]
    # Should use the higher priority tool (mock-calculator-advanced)
    assert result["results"]["calc-1"]["output"]["result"] == 4
    entries = orch.auditor.read_all()
    assert entries[-1]["tool_name"] == "mock-calculator-advanced"


@pytest.mark.asyncio
async def test_create_with_parallel_executor_matches_default(registry, router, scoper, sample_task, tmp_path):
    seq_orch = Orchestrator.create(
        registry, router=router, scoper=scoper, auditor=AuditLog(tmp_path / "seq.jsonl")
    )
    par_orch = Orchestrator.create(
        registry,
        router=router,
        scoper=scoper,
        auditor=AuditLog(tmp_path / "par.jsonl"),
        executor_cls=ParallelExecutor,
    )

    seq = await seq_orch.run_task(sample_task)
    par = await par_orch.run_task(sample_task)

    assert seq == par
    assert all(r["success"] for r in par["results"].values())


def test_no_src_module_imports_conflict():
    src_dir = Path(__file__).resolve().parents[1] / "src"
    offenders = [str(p) for p in src_dir.rglob("*.py") if "conflict" in p.read_text()]
    assert not offenders, f"conflict references remain in: {offenders}"


def test_audit_entry_removed_from_models():
    models_file = Path(__file__).resolve().parents[1] / "src" / "models.py"
    assert "AuditEntry" not in models_file.read_text()