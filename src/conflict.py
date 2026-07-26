from __future__ import annotations

import logging
from typing import Any

from .models import ToolManifest

logger = logging.getLogger(__name__)


class ConflictResolver:
    def resolve(self, tools: list[ToolManifest]) -> ToolManifest:
        if not tools:
            raise ValueError("No tools to resolve")
        if len(tools) == 1:
            return tools[0]

        best = tools[0]
        for tool in tools[1:]:
            if tool.priority > best.priority:
                best = tool

        logger.info(
            "Conflict resolved: %s (priority=%d) selected over %d other tool(s)",
            best.name, best.priority, len(tools) - 1
        )
        return best