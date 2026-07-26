from __future__ import annotations

import logging
from typing import Any

from .models import Step, ToolResult, PermissionToken
from .registry import ToolRegistry
from .router import Router
from .permission import PermissionScoper
from .conflict import ConflictResolver
from .auditor import AuditLog
from .tools import create_tool

logger = logging.getLogger(__name__)


class Executor:
    def __init__(
        self,
        registry: ToolRegistry,
        router: Router,
        scoper: PermissionScoper,
        resolver: ConflictResolver,
        auditor: AuditLog,
    ) -> None:
        self.registry = registry
        self.router = router
        self.scoper = scoper
        self.resolver = resolver
        self.auditor = auditor

    async def run(self, steps: list[Step], token: PermissionToken) -> dict[str, ToolResult]:
        results: dict[str, ToolResult] = {}
        completed: set[str] = set()
        remaining_steps = list(steps)
        max_iterations = len(steps) * 2

        iteration = 0
        while remaining_steps and iteration < max_iterations:
            iteration += 1
            progress_made = False

            for step in list(remaining_steps):
                if not self._dependencies_met(step, completed):
                    continue

                tool_manifest = self._select_tool(step)
                if not self._check_permission(tool_manifest, token):
                    result = ToolResult(
                        step_id=step.id,
                        tool_name=tool_manifest.name,
                        success=False,
                        error=f"Scope {tool_manifest.required_scope} not granted",
                    )
                    results[step.id] = result
                    self._log_audit(step, tool_manifest, result, token.task_id)
                    remaining_steps.remove(step)
                    progress_made = True
                    continue

                tool = create_tool(tool_manifest.name, tool_manifest)
                try:
                    output = await tool.execute(step.input)
                    result = ToolResult(
                        step_id=step.id,
                        tool_name=tool_manifest.name,
                        success=True,
                        output=output,
                    )
                except Exception as e:
                    result = ToolResult(
                        step_id=step.id,
                        tool_name=tool_manifest.name,
                        success=False,
                        error=str(e),
                    )

                results[step.id] = result
                self._log_audit(step, tool_manifest, result, token.task_id)

                if result.success:
                    completed.add(step.id)
                else:
                    logger.warning("Step %s failed: %s", step.id, result.error)

                remaining_steps.remove(step)
                progress_made = True

            if not progress_made:
                # Circular dependency or all remaining have unmet deps
                for step in remaining_steps:
                    result = ToolResult(
                        step_id=step.id,
                        tool_name="",
                        success=False,
                        error="Dependencies not met (circular or missing)",
                    )
                    results[step.id] = result
                break

        return results

    def _select_tool(self, step: Step) -> Any:
        tools = self.router.route(step.capability)
        return self.resolver.resolve(tools)

    def _check_permission(self, tool_manifest: Any, token: PermissionToken) -> bool:
        return tool_manifest.required_scope in token.granted_scopes

    def _dependencies_met(self, step: Step, completed: set[str]) -> bool:
        return all(dep in completed for dep in step.dependencies)

    def _log_audit(self, step: Step, tool_manifest: Any, result: ToolResult, task_id: str) -> None:
        self.auditor.log(
            task_id=task_id,
            step_id=step.id,
            tool_name=tool_manifest.name,
            scope_used=tool_manifest.required_scope,
            result=result,
        )