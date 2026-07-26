from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import ToolManifest


class BaseTool(ABC):
    def __init__(self, manifest: ToolManifest) -> None:
        self.manifest = manifest

    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        pass