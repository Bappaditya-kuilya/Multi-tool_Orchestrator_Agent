from __future__ import annotations

import pytest
from pathlib import Path

from src.models import ToolResult
from src.auditor import AuditLog


@pytest.fixture
def auditor(tmp_path: Path):
    return AuditLog(tmp_path / "audit.jsonl")


def test_append_and_read(auditor: AuditLog):
    result = ToolResult(step_id="s1", tool_name="calc", success=True, output={"result": 42}, error=None)
    auditor.log("task-1", "s1", "calc", "calc:eval", result)
    entries = auditor.read_all()
    assert len(entries) == 1
    assert entries[0]["task_id"] == "task-1"
    assert entries[0]["step_id"] == "s1"
    assert entries[0]["tool_name"] == "calc"
    assert entries[0]["status"] == "success"


def test_count_by_tool(auditor: AuditLog):
    result = ToolResult(step_id="s1", tool_name="calc", success=True, output={}, error=None)
    auditor.log("task-1", "s1", "calc", "calc:eval", result)
    auditor.log("task-1", "s2", "calc", "calc:eval", result)
    auditor.log("task-1", "s3", "weather", "weather:read", result)
    assert auditor.count_by_tool("calc") == 2
    assert auditor.count_by_tool("weather") == 1


def test_count_by_status(auditor: AuditLog):
    success = ToolResult(step_id="s1", tool_name="calc", success=True, output={}, error=None)
    failure = ToolResult(step_id="s2", tool_name="calc", success=False, output={}, error="error")
    auditor.log("task-1", "s1", "calc", "calc:eval", success)
    auditor.log("task-1", "s2", "calc", "calc:eval", failure)
    assert auditor.count_by_status("success") == 1
    assert auditor.count_by_status("failure") == 1