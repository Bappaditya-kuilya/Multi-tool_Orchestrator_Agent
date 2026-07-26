from __future__ import annotations

import pytest
from pathlib import Path
import yaml

from src.models import Step, PermissionToken
from src.registry import ToolRegistry
from src.router import Router
from src.permission import PermissionScoper
from src.conflict import ConflictResolver
from src.executor import Executor
from src.auditor import AuditLog
from src.tools.base import BaseTool
from src.tools import TOOL_CLASSES


class AlwaysFailCalculator(BaseTool):
    async def execute(self, input_data: dict) -> dict:
        raise RuntimeError("Simulated API failure")


TOOL_CLASSES["fail-calc"] = AlwaysFailCalculator


@pytest.fixture
def fallback_registry(tmp_path):
    reg = ToolRegistry()
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    (manifests_dir / "fail-calc.yaml").write_text(yaml.dump({
        "name": "fail-calc",
        "capability_tags": ["calculator"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "calculator:eval",
        "priority": 20,
    }))

    (manifests_dir / "real-calc.yaml").write_text(yaml.dump({
        "name": "real-calc",
        "capability_tags": ["calculator"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "calculator:eval",
        "priority": 10,
    }))

    reg.load_manifests(manifests_dir)
    return reg


@pytest.fixture
def fallback_executor(tmp_path, fallback_registry):
    router = Router(fallback_registry)
    scoper = PermissionScoper(fallback_registry, router)
    resolver = ConflictResolver()
    auditor = AuditLog(tmp_path / "test_fallback_audit.jsonl")
    return Executor(fallback_registry, router, scoper, resolver, auditor)


@pytest.mark.asyncio
async def test_fallback_on_tool_failure(fallback_executor):
    steps = [
        Step(id="calc-1", capability="calculator", input={"expression": "2+2"}),
    ]
    token = PermissionToken(task_id="fallback-test", granted_scopes=["calculator:eval"])

    result = await fallback_executor.run(steps, token)

    assert result["calc-1"].success
    assert result["calc-1"].tool_name == "real-calc"
    assert result["calc-1"].output["result"] == 4


@pytest.mark.asyncio
async def test_fallback_audit_trail(fallback_executor):
    steps = [
        Step(id="calc-1", capability="calculator", input={"expression": "2+2"}),
    ]
    token = PermissionToken(task_id="fallback-test", granted_scopes=["calculator:eval"])

    await fallback_executor.run(steps, token)

    entries = fallback_executor.auditor.read_all()
    assert len(entries) == 2
    assert entries[0]["tool_name"] == "fail-calc"
    assert entries[0]["status"] == "failure"
    assert entries[1]["tool_name"] == "real-calc"
    assert entries[1]["status"] == "success"
