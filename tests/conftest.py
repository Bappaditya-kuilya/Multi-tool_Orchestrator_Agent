import pytest
import threading
import yaml

from src.models import ToolManifest, Task, Step, PermissionToken, ToolResult
from src.registry import ToolRegistry
from src.router import Router
from src.permission import PermissionScoper
from src.executor import Executor
from src.auditor import AuditLog


def with_guard(fn, *args, timeout_s):
    box = {}

    def run():
        try:
            box["result"] = fn(*args)
        except BaseException as e:
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise TimeoutError(f"{fn.__name__} did not finish within {timeout_s}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


def write_manifest(manifests_dir, name, data):
    (manifests_dir / f"{name}.yaml").write_text(yaml.dump({"name": name, **data}))


@pytest.fixture
def audit_path(tmp_path):
    return tmp_path / "audit.jsonl"


@pytest.fixture
def temp_manifests_dir(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


@pytest.fixture
def sample_manifests(temp_manifests_dir):
    manifests = {
        "mock-calculator": ToolManifest(
            name="mock-calculator",
            capability_tags=["calculator"],
            input_schema={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}, "required": ["result"]},
            required_scope="calculator:eval",
            priority=10,
        ),
        "mock-calculator-advanced": ToolManifest(
            name="mock-calculator-advanced",
            capability_tags=["calculator"],
            input_schema={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}, "required": ["result"]},
            required_scope="calculator:eval",
            priority=5,
        ),
        "mock-weather": ToolManifest(
            name="mock-weather",
            capability_tags=["weather"],
            input_schema={"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
            output_schema={"type": "object", "properties": {"temp": {"type": "number"}}, "required": ["temp"]},
            required_scope="weather:read",
            priority=10,
        ),
        "mock-wikipedia": ToolManifest(
            name="mock-wikipedia",
            capability_tags=["wikipedia"],
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            output_schema={"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
            required_scope="wikipedia:read",
            priority=10,
        ),
        "mock-github-search": ToolManifest(
            name="mock-github-search",
            capability_tags=["github-search"],
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            output_schema={"type": "object", "properties": {"total_count": {"type": "integer"}}, "required": ["total_count"]},
            required_scope="github:search",
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
def auditor(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


@pytest.fixture
def executor(registry, router, scoper, auditor):
    return Executor(registry, router, scoper, auditor)


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