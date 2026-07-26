import pytest

from src.conflict import ConflictResolver
from src.models import ToolManifest


def test_resolve_single_tool(resolver):
    manifest = ToolManifest(
        name="only",
        capability_tags=["calc"],
        input_schema={},
        output_schema={},
        required_scope="calc:eval",
        priority=1,
    )
    result = resolver.resolve([manifest])
    assert result.name == "only"


def test_resolve_priority(resolver):
    m1 = ToolManifest(name="low", capability_tags=["calc"], input_schema={}, output_schema={}, required_scope="calc:eval", priority=1)
    m2 = ToolManifest(name="high", capability_tags=["calc"], input_schema={}, output_schema={}, required_scope="calc:eval", priority=10)
    result = resolver.resolve([m1, m2])
    assert result.name == "high"


def test_resolve_tie_breaks_by_load_order(resolver):
    m1 = ToolManifest(name="first", capability_tags=["calc"], input_schema={}, output_schema={}, required_scope="calc:eval", priority=5)
    m2 = ToolManifest(name="second", capability_tags=["calc"], input_schema={}, output_schema={}, required_scope="calc:eval", priority=5)
    result = resolver.resolve([m1, m2])
    assert result.name == "first"