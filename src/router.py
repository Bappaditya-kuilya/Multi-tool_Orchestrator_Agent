from __future__ import annotations

from typing import Any

from .models import ToolManifest
from .registry import ToolRegistry


class NoToolForCapability(Exception):
    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"No tool registered for capability: {capability}")


class Router:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def route(self, capability: str) -> list[ToolManifest]:
        tools = self.registry.get_tools_for_capability(capability)
        if not tools:
            raise NoToolForCapability(capability)
        return tools