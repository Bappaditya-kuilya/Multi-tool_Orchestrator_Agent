from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Task, Step, SubTask, ToolResult, PermissionToken
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
        executor.sub_task_handler = orch.run_sub_task
        return orch, task

    @classmethod
    def create(
        cls,
        registry: ToolRegistry,
        router: Router | None = None,
        scoper: PermissionScoper | None = None,
        resolver: ConflictResolver | None = None,
        auditor: AuditLog | None = None,
    ) -> "Orchestrator":
        router = router or Router(registry)
        scoper = scoper or PermissionScoper(registry, router)
        resolver = resolver or ConflictResolver()
        auditor = auditor or AuditLog(Path("audit.jsonl"))
        executor = Executor(registry, router, scoper, resolver, auditor)
        orch = cls(registry, router, scoper, resolver, executor, auditor)
        executor.sub_task_handler = orch.run_sub_task
        return orch

    def _create_child_orchestrator(self, sub_task: SubTask) -> "Orchestrator":
        child_registry = ToolRegistry()
        for tool in self.registry.all_tools():
            if not sub_task.allowed_scopes or tool.required_scope in sub_task.allowed_scopes:
                child_registry._tools[tool.name] = tool
                for cap in tool.capability_tags:
                    if cap not in child_registry._by_capability:
                        child_registry._by_capability[cap] = []
                    child_registry._by_capability[cap].append(tool)
        for cap in child_registry._by_capability:
            child_registry._by_capability[cap].sort(
                key=lambda m: (-m.priority, child_registry._tools[m.name].name)
            )

        child_router = Router(child_registry)
        child_scoper = PermissionScoper(child_registry, child_router)
        child_resolver = ConflictResolver()
        child_auditor = AuditLog(self.auditor.path.parent / f"sub_{sub_task.task_id}_audit.jsonl")
        child_executor = Executor(child_registry, child_router, child_scoper, child_resolver, child_auditor)

        child = Orchestrator(
            registry=child_registry,
            router=child_router,
            scoper=child_scoper,
            resolver=child_resolver,
            executor=child_executor,
            auditor=child_auditor,
        )
        child_executor.sub_task_handler = child.run_sub_task
        return child

    async def run_sub_task(self, sub_task: SubTask) -> dict[str, Any]:
        child = self._create_child_orchestrator(sub_task)
        token = PermissionToken(
            task_id=sub_task.task_id,
            granted_scopes=sub_task.allowed_scopes,
        )
        results = await child.executor.run(sub_task.steps, token)
        return {
            step_id: {
                "success": r.success,
                "output": r.output,
                "error": r.error,
            }
            for step_id, r in results.items()
        }

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
