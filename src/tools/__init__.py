from __future__ import annotations

from typing import Any

from .base import BaseTool
from .mock_weather import MockWeatherTool
from .mock_wikipedia import MockWikipediaTool
from .mock_calculator import MockCalculatorTool
from .mock_github import MockGitHubSearchTool


TOOL_CLASSES = {
    "mock-weather": MockWeatherTool,
    "mock-wikipedia": MockWikipediaTool,
    "mock-calculator": MockCalculatorTool,
    "mock-github-search": MockGitHubSearchTool,
    "mock-calculator-advanced": MockCalculatorTool,
}


class GenericMockTool(BaseTool):
    """Generic mock tool that returns canned responses based on capability."""
    
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        caps = self.manifest.capability_tags
        if "calculator" in caps:
            return {"expression": input_data.get("expression", ""), "result": 4}
        if "weather" in caps:
            return {"location": input_data.get("location", ""), "temperature_c": 20, "condition": "Clear", "humidity": 50}
        if "wikipedia" in caps:
            return {"title": input_data.get("query", ""), "summary": "Mock summary", "url": "https://example.com"}
        if "github-search" in caps:
            return {"total_count": 1, "items": [{"name": "mock", "full_name": "user/mock", "html_url": "https://github.com/user/mock"}]}
        return {"result": "mock"}


def create_tool(name: str, manifest: Any) -> BaseTool:
    cls = TOOL_CLASSES.get(name)
    if cls is None:
        # Fallback to generic mock tool
        cls = GenericMockTool
    return cls(manifest)