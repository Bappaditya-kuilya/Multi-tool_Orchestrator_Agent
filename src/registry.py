from pathlib import Path
from typing import Any
import yaml

from .models import ToolManifest


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolManifest] = {}
        self._by_capability: dict[str, list[ToolManifest]] = {}

    def load_manifests(self, path: Path) -> None:
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
        return self._tools.get(name)

    def get_tools_for_capability(self, capability: str) -> list[ToolManifest]:
        return self._by_capability.get(capability, [])

    def all_tools(self) -> list[ToolManifest]:
        return list(self._tools.values())

    def all_capabilities(self) -> list[str]:
        return list(self._by_capability.keys())