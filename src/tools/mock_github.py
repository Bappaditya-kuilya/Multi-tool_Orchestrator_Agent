from __future__ import annotations

import asyncio
from typing import Any

from .base import BaseTool


class MockGitHubSearchTool(BaseTool):
    REPOS = {
        "pydantic": {
            "name": "pydantic",
            "full_name": "pydantic/pydantic",
            "description": "Data validation using Python type hints",
            "stargazers_count": 15000,
            "html_url": "https://github.com/pydantic/pydantic",
        },
        "fastapi": {
            "name": "fastapi",
            "full_name": "tiangolo/fastapi",
            "description": "FastAPI framework, high performance, easy to learn, fast to code",
            "stargazers_count": 65000,
            "html_url": "https://github.com/tiangolo/fastapi",
        },
        "httpx": {
            "name": "httpx",
            "full_name": "encode/httpx",
            "description": "A next generation HTTP client for Python",
            "stargazers_count": 12000,
            "html_url": "https://github.com/encode/httpx",
        },
    }

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.5)
        query = input_data.get("query", "pydantic")
        per_page = input_data.get("per_page", 10)
        repo = self.REPOS.get(query, self.REPOS["pydantic"])
        return {
            "total_count": 42,
            "items": [repo][:per_page],
        }