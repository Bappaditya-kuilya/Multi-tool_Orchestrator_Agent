from __future__ import annotations

import contextvars
import json
from pathlib import Path
from typing import Any

from .models import Task, Step, SubTask, ToolResult, PermissionToken
from .registry import ToolRegistry
from .router import Router
from .permission import PermissionScoper
from .executor import Executor
from .auditor import AuditLog, sanitize_filename_stem


class TaskFileError(Exception):
    """Task file (or its manifests) could not be loaded or parsed."""


class SubTaskDepthError(Exception):
    """Sub-task nesting exceeded the configured depth cap."""


# ponytail: fixed depth cap, config later if real DAGs need it
SUB_TASK_MAX_DEPTH = 50
_sub_task_depth: contextvars.ContextVar[int] = contextvars.ContextVar("sub_task_depth", default=0)


class Orchestrator:
    def __init__(
        self,
        registry: ToolRegistry,
        router: Router,
        scoper: PermissionScoper,
        executor: Executor,
        auditor: AuditLog,
    ) -> None:
        self.registry = registry
        self.router = router
        self.scoper = scoper
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
        try:
            registry.load_manifests(Path(manifests_dir))
        except Exception as e:
            raise TaskFileError(f"cannot load manifests from {manifests_dir}: {e}") from e

        router = Router(registry)
        scoper = PermissionScoper(registry, router)
        auditor = AuditLog(Path(audit_file))
        executor = Executor(registry, router, scoper, auditor)

        try:
            task_data = json.loads(Path(task_file).read_text())
        except Exception as e:
            raise TaskFileError(f"cannot load task file {task_file}: {e}") from e
        try:
            task = Task(
                task_id=task_data["task_id"],
                steps=[Step(**s) for s in task_data["steps"]],
            )
        except Exception as e:
            raise TaskFileError(f"invalid task file {task_file}: {e}") from e

        orch = cls(registry, router, scoper, executor, auditor)
        executor.sub_task_handler = orch.run_sub_task
        return orch, task

    @classmethod
    def create(
        cls,
        registry: ToolRegistry,
        router: Router | None = None,
        scoper: PermissionScoper | None = None,
        auditor: AuditLog | None = None,
        executor_cls: type[Executor] = Executor,
    ) -> "Orchestrator":
        router = router or Router(registry)
        scoper = scoper or PermissionScoper(registry, router)
        auditor = auditor or AuditLog(Path("audit.jsonl"))
        executor = executor_cls(registry, router, scoper, auditor)
        orch = cls(registry, router, scoper, executor, auditor)
        executor.sub_task_handler = orch.run_sub_task
        return orch

    def _create_child_orchestrator(self, sub_task: SubTask, allowed_scopes: list[str], parent_token: PermissionToken) -> "Orchestrator":
        # ponytail: deny when intersection empty; never prune child registry to empty
        if not allowed_scopes:
            raise ValueError("No allowed scopes intersect with parent token")
        
        child_registry = ToolRegistry()
        for tool in self.registry.all_tools():
            if tool.required_scope in allowed_scopes:
                child_registry._tools[tool.name] = tool
                for cap in tool.capability_tags:
                    if cap not in child_registry._by_capability:
                        child_registry._by_capability[cap] = []
                    child_registry._by_capability[cap].append(tool)
        
        # ponytail: if no tools match allowed scopes, deny rather than give empty registry
        if not child_registry._tools:
            raise ValueError("No tools available for allowed scopes")
            
        for cap in child_registry._by_capability:
            child_registry._by_capability[cap].sort(
                key=lambda m: (-m.priority, child_registry._tools[m.name].name)
            )

        child_router = Router(child_registry)
        child_scoper = PermissionScoper(child_registry, child_router)
        child_auditor = AuditLog(self.auditor.path.parent / f"sub_{sanitize_filename_stem(sub_task.task_id)}_audit.jsonl")
        child_executor = Executor(child_registry, child_router, child_scoper, child_auditor)

        child = Orchestrator(
            registry=child_registry,
            router=child_router,
            scoper=child_scoper,
            executor=child_executor,
            auditor=child_auditor,
        )
        child_executor.sub_task_handler = child.run_sub_task
        return child

    async def run_sub_task(self, sub_task: SubTask, parent_token: PermissionToken) -> dict[str, Any]:
        if _sub_task_depth.get() >= SUB_TASK_MAX_DEPTH:
            raise SubTaskDepthError(
                f"Sub-task depth exceeds limit of {SUB_TASK_MAX_DEPTH}"
            )
        depth_token = _sub_task_depth.set(_sub_task_depth.get() + 1)
        try:
            # ponytail: compute intersection of allowed_scopes with parent token
            allowed_scopes = [s for s in sub_task.allowed_scopes if s in parent_token.granted_scopes]
            if not allowed_scopes:
                return {
                    step.id: {
                        "success": False,
                        "output": None,
                        "error": "Scope not granted by parent token",
                    }
                    for step in sub_task.steps
                }
            child = self._create_child_orchestrator(sub_task, allowed_scopes, parent_token)
            token = PermissionToken(
                task_id=sub_task.task_id,
                granted_scopes=allowed_scopes,
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
        finally:
            _sub_task_depth.reset(depth_token)

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
