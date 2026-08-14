from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ToolResult


def sanitize_filename_stem(stem: str) -> str:
    """Replace characters unsafe for filenames with underscores."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", stem)


class AuditLog:
    """Append-only JSONL audit trail of every tool invocation."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        task_id: str,
        step_id: str,
        tool_name: str,
        scope_used: str,
        result: ToolResult,
    ) -> None:
        """Append one JSON line recording a step's outcome."""
        entry = {
            "task_id": task_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "scope_used": scope_used,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success" if result.success else "failure",
            "error": result.error,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        """All logged entries; corrupt or empty lines are skipped."""
        if not self.path.exists():
            return []
        entries = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
        return entries

    def count_by_tool(self, tool_name: str) -> int:
        """Number of logged entries for a given tool."""
        return sum(1 for e in self.read_all() if e.get("tool_name") == tool_name)

    def count_by_status(self, status: str) -> int:
        """Number of logged entries with the given status."""
        return sum(1 for e in self.read_all() if e.get("status") == status)