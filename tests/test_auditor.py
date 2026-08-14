from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models import ToolResult
from src.auditor import AuditLog, sanitize_filename_stem


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


def test_read_all_skips_corrupt_lines(auditor: AuditLog):
    result = ToolResult(step_id="s1", tool_name="calc", success=True, output={}, error=None)
    auditor.log("task-1", "s1", "calc", "calc:eval", result)
    with auditor.path.open("a") as f:
        f.write("this is not json at all\n")
        f.write('["not", "a", "dict"]\n')
    entries = auditor.read_all()
    assert len(entries) == 1
    assert entries[0]["tool_name"] == "calc"
    assert auditor.count_by_tool("calc") == 1
    assert auditor.count_by_status("success") == 1


def test_timestamps_tz_aware_utc(auditor: AuditLog):
    result = ToolResult(step_id="s1", tool_name="calc", success=True, output={}, error=None)
    auditor.log("task-1", "s1", "calc", "calc:eval", result)
    raw = auditor.read_all()[0]["timestamp"]
    dt = datetime.fromisoformat(raw[:-1] if raw.endswith("Z") else raw)
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(0)


def test_child_audit_filename_sanitized(tmp_path: Path):
    parent = tmp_path / "audits"
    sanitized = sanitize_filename_stem("a/b")
    assert sanitized == "a_b"
    assert re.fullmatch(r"[A-Za-z0-9_-]+", sanitized)
    child = AuditLog(parent / f"sub_{sanitized}_audit.jsonl")
    child.log(
        "a/b",
        "s1",
        "calc",
        "calc:eval",
        ToolResult(step_id="s1", tool_name="calc", success=True, output={}, error=None),
    )
    assert not (parent / "sub_a").exists()
    assert (parent / "sub_a_b_audit.jsonl").is_file()