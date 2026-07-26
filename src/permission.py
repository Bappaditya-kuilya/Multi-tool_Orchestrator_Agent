from __future__ import annotations

from typing import Any

from .models import Task, PermissionToken, Step
from .registry import ToolRegistry
from .router import Router, NoToolForCapability


class PermissionScoper:
    def __init__(self, registry: ToolRegistry, router: Router) -> None:
        self.registry = registry
        self.router = router

    def issue_token(self, task: Task) -> PermissionToken:
        scopes: set[str] = set()

        for step in task.steps:
            try:
                tools = self.router.route(step.capability)
                for tool in tools:
                    scopes.add(tool.required_scope)
            except NoToolForCapability:
                continue

        return PermissionToken(task_id=task.task_id, granted_scopes=list(scopes))

    def check_scope(self, scope: str, token: PermissionToken) -> bool:
        return scope in token.granted_scopes