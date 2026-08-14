from __future__ import annotations

import pytest

from src.models import ToolManifest
from src.tools import create_tool
from src.tools.mock_calculator import MockCalculatorTool, safe_eval
from src.tools.mock_github import MockGitHubSearchTool
from src.tools.mock_weather import MockWeatherTool


def make_manifest(name: str = "test-tool") -> ToolManifest:
    return ToolManifest(name=name, required_scope="test:read")


@pytest.fixture
def github() -> MockGitHubSearchTool:
    return MockGitHubSearchTool(make_manifest("github"))


@pytest.fixture
def weather() -> MockWeatherTool:
    return MockWeatherTool(make_manifest("weather"))


@pytest.fixture
def base_calc() -> MockCalculatorTool:
    return MockCalculatorTool(make_manifest("calc"))


@pytest.mark.asyncio
async def test_github_per_page_string_no_typeerror(github):
    result = await github.execute({"query": "pydantic", "per_page": "abc"})
    assert result["items"] == [github.REPOS["pydantic"]]


@pytest.mark.asyncio
async def test_github_per_page_negative_clamped(github):
    result = await github.execute({"query": "pydantic", "per_page": -5})
    assert len(result["items"]) == 1


@pytest.mark.asyncio
async def test_github_per_page_huge_clamped(github):
    result = await github.execute({"query": "pydantic", "per_page": 10**9})
    assert len(result["items"]) == 1


@pytest.mark.asyncio
async def test_github_unknown_query_returns_empty(github):
    result = await github.execute({"query": "nonexistent-repo"})
    assert result["items"] == []
    assert result["total_count"] == 0


@pytest.mark.asyncio
async def test_weather_seeded_deterministic(weather):
    runs = [await weather.execute({"location": "London", "seed": 42}) for _ in range(5)]
    temps = {r["temperature_c"] for r in runs}
    assert len(temps) == 1


def test_calculator_overflow_constant_fails():
    with pytest.raises(ValueError):
        safe_eval("1e1000")


@pytest.mark.asyncio
async def test_calculator_overflow_constant_tool_fails(base_calc):
    with pytest.raises(ValueError):
        await base_calc.execute({"expression": "1e1000"})


def test_unknown_tool_name_raises_value_error():
    with pytest.raises(ValueError, match="Unknown tool: does-not-exist"):
        create_tool("does-not-exist", make_manifest("does-not-exist"))


def test_unknown_tool_never_returns_a_tool():
    try:
        result = create_tool("does-not-exist", make_manifest("does-not-exist"))
    except ValueError:
        return
    assert result is None


@pytest.mark.asyncio
async def test_advanced_routes_to_advanced_tool_not_base():
    from src.tools.mock_calculator_advanced import MockCalculatorAdvancedTool

    tool = create_tool("mock-calculator-advanced", make_manifest("adv"))
    assert isinstance(tool, MockCalculatorAdvancedTool)
    assert not isinstance(tool, MockCalculatorTool)


@pytest.mark.asyncio
async def test_advanced_sqrt():
    from src.tools.mock_calculator_advanced import MockCalculatorAdvancedTool

    tool = MockCalculatorAdvancedTool(make_manifest("adv"))
    result = await tool.execute({"expression": "sqrt(16)"})
    assert result["result"] == 4.0


@pytest.mark.asyncio
async def test_advanced_abs():
    from src.tools.mock_calculator_advanced import MockCalculatorAdvancedTool

    tool = MockCalculatorAdvancedTool(make_manifest("adv"))
    result = await tool.execute({"expression": "abs(-3)"})
    assert result["result"] == 3.0


@pytest.mark.asyncio
async def test_advanced_sqrt_not_in_base(base_calc):
    with pytest.raises(ValueError):
        await base_calc.execute({"expression": "sqrt(16)"})


@pytest.mark.asyncio
async def test_advanced_pow_bound_inherited():
    from src.tools.mock_calculator_advanced import MockCalculatorAdvancedTool

    tool = MockCalculatorAdvancedTool(make_manifest("adv"))
    with pytest.raises(ValueError):
        await tool.execute({"expression": "9**9**9"})


def test_calculator_mul_overflow_result_fails():
    with pytest.raises(ValueError):
        safe_eval("1e308*10")


@pytest.mark.asyncio
async def test_advanced_sqrt_overflow_result_fails():
    from src.tools.mock_calculator_advanced import MockCalculatorAdvancedTool

    tool = MockCalculatorAdvancedTool(make_manifest("adv"))
    with pytest.raises(ValueError):
        await tool.execute({"expression": "sqrt(1e308*10)"})
