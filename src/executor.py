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

                result = await self._run_with_fallback(step, token)
                results[step.id] = result

                if result.success:
                    completed.add(step.id)
                else:
                    logger.warning("Step %s failed after all fallbacks: %s", step.id, result.error)

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

    def _select_tools(self, step: Step) -> list[Any]:
        return self.router.route(step.capability)

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

    async def _run_with_fallback(self, step: Step, token: PermissionToken) -> ToolResult:
        tools = self._select_tools(step)
        last_result = None

        for tool_manifest in tools:
            if not self._check_permission(tool_manifest, token):
                last_result = ToolResult(
                    step_id=step.id,
                    tool_name=tool_manifest.name,
                    success=False,
                    error=f"Scope {tool_manifest.required_scope} not granted",
                )
                self._log_audit(step, tool_manifest, last_result, token.task_id)
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
                self._log_audit(step, tool_manifest, result, token.task_id)
                return result
            except Exception as e:
                result = ToolResult(
                    step_id=step.id,
                    tool_name=tool_manifest.name,
                    success=False,
                    error=str(e),
                )
                self._log_audit(step, tool_manifest, result, token.task_id)
                last_result = result
                logger.warning("Tool %s failed for step %s: %s, trying next fallback", tool_manifest.name, step.id, e)

        return last_result or ToolResult(
            step_id=step.id,
            tool_name="",
            success=False,
            error="All fallback tools failed or no tools available",
        )


class ParallelExecutor:
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
        import asyncio
        results: dict[str, ToolResult] = {}
        completed: set[str] = set()
        remaining_steps = {s.id: s for s in steps}

        while remaining_steps:
            ready_batch = [
                step for step in remaining_steps.values()
                if all(dep in completed for dep in step.dependencies)
            ]

            if not ready_batch:
                for step in remaining_steps.values():
                    results[step.id] = ToolResult(
                        step_id=step.id,
                        tool_name="",
                        success=False,
                        error="Dependencies not met (circular or missing)",
                    )
                break

            batch_coros = [self._run_step(step, token, task_id=token.task_id) for step in ready_batch]
            batch_results = await asyncio.gather(*batch_coros, return_exceptions=True)

            for step, result in zip(ready_batch, batch_results):
                if isinstance(result, Exception):
                    result = ToolResult(
                        step_id=step.id,
                        tool_name="",
                        success=False,
                        error=str(result),
                    )

                results[step.id] = result
                if result.success:
                    completed.add(step.id)

                del remaining_steps[step.id]

        return results

    async def _run_step(self, step: Step, token: PermissionToken, task_id: str) -> ToolResult:
        tools = self._select_tools(step)
        last_result = None

        for tool_manifest in tools:
            if not self._check_permission(tool_manifest, token):
                last_result = ToolResult(
                    step_id=step.id,
                    tool_name=tool_manifest.name,
                    success=False,
                    error=f"Scope {tool_manifest.required_scope} not granted",
                )
                self._log_audit(step, tool_manifest, last_result, task_id)
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
                self._log_audit(step, tool_manifest, result, task_id)
                return result
            except Exception as e:
                result = ToolResult(
                    step_id=step.id,
                    tool_name=tool_manifest.name,
                    success=False,
                    error=str(e),
                )
                self._log_audit(step, tool_manifest, result, task_id)
                last_result = result
                logger.warning("Tool %s failed for step %s: %s, trying next fallback", tool_manifest.name, step.id, e)

        return last_result or ToolResult(
            step_id=step.id,
            tool_name="",
            success=False,
            error="All fallback tools failed or no tools available",
        )

    def _select_tools(self, step: Step) -> list[Any]:
        return self.router.route(step.capability)

    def _check_permission(self, tool_manifest: Any, token: PermissionToken) -> bool:
        return tool_manifest.required_scope in token.granted_scopes

    def _log_audit(self, step: Step, tool_manifest: Any, result: ToolResult, task_id: str) -> None:
        self.auditor.log(
            task_id=task_id,
            step_id=step.id,
            tool_name=tool_manifest.name,
            scope_used=tool_manifest.required_scope,
            result=result,
        )