from __future__ import annotations

import pytest

from src.models import ToolManifest
from src.registry import ToolRegistry


@pytest.fixture
def registry(tmp_path):
    reg = ToolRegistry()
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "mock-weather.yaml").write_text("""
name: "mock-weather"
capability_tags: ["weather"]
input_schema: {"type": "object", "properties": {}}
output_schema: {"type": "object", "properties": {}}
required_scope: "weather:read"
priority: 10
""")
    reg.load_manifests(manifests_dir)
    return reg


def test_load_manifests(registry):
    assert "mock-weather" in registry._tools
    assert registry._tools["mock-weather"].name == "mock-weather"


def test_get_tools_for_capability(registry):
    tools = registry.get_tools_for_capability("weather")
    assert len(tools) == 1
    assert tools[0].name == "mock-weather"


def test_duplicate_name_raises(tmp_path):
    reg = ToolRegistry()
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "a.yaml").write_text("""
name: "mock-weather"
capability_tags: ["weather"]
input_schema: {}
output_schema: {}
required_scope: "weather:read"
priority: 10
""")
    (manifests_dir / "b.yaml").write_text("""
name: "mock-weather"
capability_tags: ["weather"]
input_schema: {}
output_schema: {}
required_scope: "weather:read"
priority: 5
""")
    with pytest.raises(ValueError, match="Duplicate tool name"):
        reg.load_manifests(manifests_dir)