from __future__ import annotations

from typing import Any

from .models import ToolManifest
from .registry import ToolRegistry
from .semantic import SemanticMatcher


class NoToolForCapability(Exception):
    """Raised when no registered tool matches the requested capability."""

    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"No tool registered for capability: {capability}")


class Router:
    """Maps a capability to candidate tools, via exact tags or semantic fallback."""

    def __init__(self, registry: ToolRegistry, use_semantic: bool = False, threshold: float = 0.3) -> None:
        self.registry = registry
        self.use_semantic = use_semantic
        self.threshold = threshold
        self._semantic: SemanticMatcher | None = None
        if use_semantic:
            self._build_semantic_index()

    def _build_semantic_index(self) -> None:
        docs = []
        for tool in self.registry.all_tools():
            text = f"{tool.name} {' '.join(tool.capability_tags)}"
            if hasattr(tool, 'description') and tool.description:
                text += f" {tool.description}"
            docs.append(text)
        self._semantic = SemanticMatcher(docs)

    def route(self, capability: str) -> list[ToolManifest]:
        """Return tools for a capability (exact tag match first, semantic if enabled)."""
        tools = self.registry.get_tools_for_capability(capability)
        if tools:
            return tools

        if self.use_semantic and self._semantic:
            return self._semantic_route(capability)

        raise NoToolForCapability(capability)

    def _semantic_route(self, capability: str) -> list[ToolManifest]:
        all_tools = self.registry.all_tools()
        if not all_tools:
            raise NoToolForCapability(capability)

        candidates = []
        for tool in all_tools:
            text = f"{tool.name} {' '.join(tool.capability_tags)}"
            if hasattr(tool, 'description') and tool.description:
                text += f" {tool.description}"
            candidates.append(text)

        ranked = self._semantic.rank(capability, candidates)
        matched_tools = []
        for doc, score in ranked:
            if score < self.threshold:
                break
            idx = candidates.index(doc)
            matched_tools.append(all_tools[idx])

        if not matched_tools:
            raise NoToolForCapability(capability)

        return matched_tools

    def route_step(self, step: Any) -> list[ToolManifest]:
        """Route a single Step by its capability."""
        return self.route(step.capability)
