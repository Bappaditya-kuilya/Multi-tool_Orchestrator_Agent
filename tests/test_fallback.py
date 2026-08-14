from __future__ import annotations

import pytest

from src.models import Step, PermissionToken
from src.registry import ToolRegistry
from src.router import Router
from src.permission import PermissionScoper
from src.executor import Executor
from src.auditor import AuditLog
from src.tools.base import BaseTool
from src.tools import TOOL_CLASSES
from conftest import write_manifest


class AlwaysFailCalculator(BaseTool):
    async def execute(self, input_data: dict) -> dict:
        raise RuntimeError("Simulated API failure")


TOOL_CLASSES["fail-calc"] = AlwaysFailCalculator


@pytest.fixture
def fallback_registry(temp_manifests_dir, sample_manifests):
    write_manifest(temp_manifests_dir, "fail-calc", {
        "capability_tags": ["calculator"],
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "required_scope": "calculator:eval",
        "priority": 20,
    })
    reg = ToolRegistry()
    reg.load_manifests(temp_manifests_dir)
    return reg


@pytest.fixture
def fallback_executor(fallback_registry, audit_path):
    router = Router(fallback_registry)
    scoper = PermissionScoper(fallback_registry, router)
    return Executor(fallback_registry, router, scoper, AuditLog(audit_path))


@pytest.mark.asyncio
async def test_fallback_on_tool_failure(fallback_executor):
    steps = [
        Step(id="calc-1", capability="calculator", input={"expression": "2+2"}),
    ]
    token = PermissionToken(task_id="fallback-test", granted_scopes=["calculator:eval"])

    result = await fallback_executor.run(steps, token)

    assert result["calc-1"].success
    assert result["calc-1"].tool_name == "mock-calculator"
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
    assert entries[1]["tool_name"] == "mock-calculator"
    assert entries[1]["status"] == "success"
