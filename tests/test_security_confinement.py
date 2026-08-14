from src.models import PermissionToken, Step, SubTask
from src.registry import ToolRegistry
from src.orchestrator import Orchestrator
from src.auditor import AuditLog

from conftest import write_manifest


def _build_orch(tmp_path):
    write_manifest(tmp_path, "mock-github-search", {
        "capability_tags": ["github-search"],
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        "output_schema": {"type": "object", "properties": {"total_count": {"type": "integer"}}},
        "required_scope": "github:search",
        "priority": 10,
    })
    write_manifest(tmp_path, "mock-calculator", {
        "capability_tags": ["calculator"],
        "input_schema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        "output_schema": {"type": "object", "properties": {"result": {"type": "number"}}},
        "required_scope": "calculator:eval",
        "priority": 10,
    })
    reg = ToolRegistry()
    reg.load_manifests(tmp_path)
    return Orchestrator.create(reg, auditor=AuditLog(tmp_path / "audit.jsonl"))


async def test_child_cannot_run_scope_parent_never_granted(tmp_path):
    orch = _build_orch(tmp_path)
    parent = PermissionToken(task_id="parent", granted_scopes=["calculator:eval"])
    sub = SubTask(
        task_id="evil-sub",
        steps=[Step(id="gh-1", capability="github-search", input={"query": "pydantic"})],
        allowed_scopes=["github:search"],
    )
    out = await orch.run_sub_task(sub, parent)
    assert out["gh-1"]["success"] is False
    assert "not granted" in out["gh-1"]["error"]
