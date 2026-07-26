from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Task, Step, ToolResult, PermissionToken
from .registry import ToolRegistry
from .router import Router
from .permission import PermissionScoper
from .conflict import ConflictResolver
from .executor import Executor
from .auditor import AuditLog
from .tools import create_tool


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        router: Router,
        scoper: PermissionScoper,
        resolver: ConflictResolver,
        executor: Executor,
        auditor: AuditLog,
    ) -> None:
        self.registry = registry
        self.router = router
        self.scoper = scoper
        self.resolver = resolver
        self.executor = executor
        self.auditor = auditor

    @classmethod
    def from_task_file(
        cls,
        task_file: Path | str,
        manifests_dir: Path | str,
        audit_file: Path | str,
    ) -> tuple["Orchestrator", Task]:
        registry = ToolRegistry()
        registry.load_manifests(Path(manifests_dir))

        router = Router(registry)
        scoper = PermissionScoper(registry, router)
        resolver = ConflictResolver()
        auditor = AuditLog(Path(audit_file))
        executor = Executor(registry, router, scoper, resolver, auditor)

        task_data = json.loads(Path(task_file).read_text())
        task = Task(
            task_id=task_data["task_id"],
            steps=[Step(**s) for s in task_data["steps"]],
        )

        orch = cls(registry, router, scoper, resolver, executor, auditor)
        return orch, task

    async def run_task(self, task: Task) -> dict[str, Any]:
        token = self.scoper.issue_token(task)
        results = await self.executor.run(task.steps, token)
        return self._format_results(task.task_id, results)

    def _format_results(self, task_id: str, results: dict[str, ToolResult]) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "results": {
                step_id: {
                    "success": r.success,
                    "output": r.output,
                    "error": r.error,
                }
                for step_id, r in results.items()
            }
        }