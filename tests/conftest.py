import pytest
import asyncio
from pathlib import Path
import tempfile
import json
import yaml

from src.models import ToolManifest, Task, Step, PermissionToken, ToolResult
from src.registry import ToolRegistry
from src.router import Router
from src.permission import PermissionScoper
from src.conflict import ConflictResolver
from src.executor import Executor
from src.auditor import AuditLog


@pytest.fixture
def temp_manifests_dir(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


@pytest.fixture
def sample_manifests(temp_manifests_dir):
    manifests = {
        "calc": ToolManifest(
            name="calc",
            capability_tags=["calculator"],
            input_schema={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}, "required": ["result"]},
            required_scope="calculator:eval",
            priority=10,
        ),
        "calc2": ToolManifest(
            name="calc2",
            capability_tags=["calculator"],
            input_schema={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}, "required": ["result"]},
            required_scope="calculator:eval",
            priority=5,
        ),
        "weather": ToolManifest(
            name="weather",
            capability_tags=["weather"],
            input_schema={"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
            output_schema={"type": "object", "properties": {"temp": {"type": "number"}}, "required": ["temp"]},
            required_scope="weather:read",
            priority=10,
        ),
    }
    for name, manifest in manifests.items():
        (temp_manifests_dir / f"{name}.yaml").write_text(yaml.dump(manifest.model_dump()))
    return manifests


@pytest.fixture
def registry(sample_manifests, temp_manifests_dir):
    r = ToolRegistry()
    r.load_manifests(temp_manifests_dir)
    return r


@pytest.fixture
def router(registry):
    return Router(registry)


@pytest.fixture
def scoper(registry, router):
    return PermissionScoper(registry, router)


@pytest.fixture
def resolver():
    return ConflictResolver()


@pytest.fixture
def auditor(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


@pytest.fixture
def executor(registry, router, scoper, resolver, auditor):
    return Executor(registry, router, scoper, resolver, auditor)


@pytest.fixture
def sample_task():
    return Task(
        task_id="test-1",
        steps=[
            Step(id="s1", capability="calculator", input={"expression": "1+1"}, dependencies=[]),
            Step(id="s2", capability="weather", input={"location": "London"}, dependencies=[]),
        ],
    )


@pytest.fixture
def sample_token():
    return PermissionToken(task_id="test", granted_scopes=["calculator:eval", "weather:read"])