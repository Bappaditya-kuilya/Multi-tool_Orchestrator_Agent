from __future__ import annotations

from typing import Any

from .base import BaseTool
from .mock_weather import MockWeatherTool
from .mock_wikipedia import MockWikipediaTool
from .mock_calculator import MockCalculatorTool
from .mock_calculator_advanced import MockCalculatorAdvancedTool
from .mock_github import MockGitHubSearchTool


TOOL_CLASSES = {
    "mock-weather": MockWeatherTool,
    "mock-wikipedia": MockWikipediaTool,
    "mock-calculator": MockCalculatorTool,
    "mock-github-search": MockGitHubSearchTool,
    "mock-calculator-advanced": MockCalculatorAdvancedTool,
}


def create_tool(name: str, manifest: Any) -> BaseTool:
    cls = TOOL_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"Unknown tool: {name}")
    return cls(manifest)