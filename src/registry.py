from pathlib import Path
from typing import Any
import yaml

from .models import ToolManifest


class ToolRegistry:
    """Loads YAML tool manifests and indexes them by name and capability."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolManifest] = {}
        self._by_capability: dict[str, list[ToolManifest]] = {}

    def load_manifests(self, path: Path) -> None:
        """Load all *.yaml manifests from a directory, raising on duplicates."""
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"Manifest directory not found: {path}")

        for manifest_file in sorted(path.glob("*.yaml")):
            with open(manifest_file) as f:
                data = yaml.safe_load(f)

            manifest = ToolManifest(**data)

            if manifest.name in self._tools:
                raise ValueError(f"Duplicate tool name: {manifest.name}")

            self._tools[manifest.name] = manifest

            for cap in manifest.capability_tags:
                if cap not in self._by_capability:
                    self._by_capability[cap] = []
                self._by_capability[cap].append(manifest)

        for cap in self._by_capability:
            self._by_capability[cap].sort(key=lambda m: (-m.priority, self._tools[m.name].name))

    def get_tool(self, name: str) -> ToolManifest | None:
        """Look up a manifest by tool name; None if not registered."""
        return self._tools.get(name)

    def get_tools_for_capability(self, capability: str) -> list[ToolManifest]:
        """Candidate tools for a capability, sorted by priority (highest first)."""
        return self._by_capability.get(capability, [])

    def all_tools(self) -> list[ToolManifest]:
        """All registered manifests, in load order."""
        return list(self._tools.values())

    def all_capabilities(self) -> list[str]:
        """Every capability tag seen across loaded manifests."""
        return list(self._by_capability.keys())