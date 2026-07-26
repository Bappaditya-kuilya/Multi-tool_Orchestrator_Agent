from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ToolResult


class AuditLog:
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
        entry = {
            "task_id": task_id,
            "step_id": step_id,
            "tool_name": tool_name,
            "scope_used": scope_used,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success" if result.success else "failure",
            "error": result.error,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def count_by_tool(self, tool_name: str) -> int:
        return sum(1 for e in self.read_all() if e["tool_name"] == tool_name)

    def count_by_status(self, status: str) -> int:
        return sum(1 for e in self.read_all() if e["status"] == status)