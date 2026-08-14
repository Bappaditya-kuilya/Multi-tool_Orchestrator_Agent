from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from .models import Step, ToolResult, PermissionToken, SubTask
from .registry import ToolRegistry
from .router import Router, NoToolForCapability
from .permission import PermissionScoper
from .auditor import AuditLog
from .tools import create_tool

logger = logging.getLogger(__name__)

SubTaskHandler = Callable[[SubTask, PermissionToken], Awaitable[dict[str, Any]]]


def _validate_unique_step_ids(steps: list[Step]) -> None:
    seen: set[str] = set()
    for step in steps:
        if step.id in seen:
            raise ValueError(f"Duplicate step id: {step.id}")
        seen.add(step.id)


class Executor:
    # ponytail: single fallback loop shared by sequential and parallel runs
    def __init__(
        self,
        registry: ToolRegistry,
        router: Router,
        scoper: PermissionScoper,
        auditor: AuditLog,
        sub_task_handler: SubTaskHandler | None = None,
    ) -> None:
        self.registry = registry
        self.router = router
        self.scoper = scoper
        self.auditor = auditor
        self.sub_task_handler = sub_task_handler

    async def run(self, steps: list[Step], token: PermissionToken) -> dict[str, ToolResult]:
        _validate_unique_step_ids(steps)
        results: dict[str, ToolResult] = {}
        completed: set[str] = set()
        remaining_steps = list(steps)
        # ponytail: one pass per step; each pass removes >=1 step or breaks
        max_iterations = len(steps)

        iteration = 0
        while remaining_steps and iteration < max_iterations:
            iteration += 1
            progress_made = False

            for step in list(remaining_steps):
                if not self._dependencies_met(step, completed):
                    continue

                result = await self._execute_step(step, token, task_id=token.task_id)
                results[step.id] = result

                if result.success:
                    completed.add(step.id)
                else:
                    logger.warning("Step %s failed after all fallbacks: %s", step.id, result.error)

                remaining_steps.remove(step)
                progress_made = True

            if not progress_made:
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

    def _dependencies_met(self, step: Step, completed: set[str]) -> bool:
        return all(dep in completed for dep in step.dependencies)

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

    async def _execute_step(self, step: Step, token: PermissionToken, task_id: str) -> ToolResult:
        if step.sub_task:
            if not self.sub_task_handler:
                return ToolResult(
                    step_id=step.id,
                    tool_name="sub-task",
                    success=False,
                    error="No sub-task handler",
                )
            return await self._run_sub_task(step, token)

        try:
            tools = self._select_tools(step)
        except NoToolForCapability:
            return ToolResult(
                step_id=step.id,
                tool_name="",
                success=False,
                error=f"No tool for capability: {step.capability}",
            )
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

    async def _run_sub_task(self, step: Step, token: PermissionToken) -> ToolResult:
        if not step.sub_task.steps:
            return ToolResult(
                step_id=step.id,
                tool_name="sub-task",
                success=False,
                error="Sub-task has no steps",
            )
        try:
            sub_results = await self.sub_task_handler(step.sub_task, token)
            for entry in sub_results.values():
                if not entry.get("success"):
                    return ToolResult(
                        step_id=step.id,
                        tool_name="sub-task",
                        success=False,
                        error=f"Sub-task failed: {entry.get('error') or 'unknown error'}",
                    )
            return ToolResult(
                step_id=step.id,
                tool_name="sub-task",
                success=True,
                output={"sub_task_id": step.sub_task.task_id, "results": sub_results},
            )
        except Exception as e:
            return ToolResult(
                step_id=step.id,
                tool_name="sub-task",
                success=False,
                error=str(e),
            )


class ParallelExecutor(Executor):
    async def run(self, steps: list[Step], token: PermissionToken) -> dict[str, ToolResult]:
        _validate_unique_step_ids(steps)
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

            batch_coros = [self._execute_step(step, token, task_id=token.task_id) for step in ready_batch]
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
