from pydantic import BaseModel, Field
from typing import Any
from datetime import datetime


class ToolManifest(BaseModel):
    name: str
    display_name: str | None = None
    description: str | None = None
    capability_tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    required_scope: str
    priority: int = 0


class SubTask(BaseModel):
    task_id: str
    steps: list["Step"] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=list)


class Step(BaseModel):
    id: str
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    sub_task: SubTask | None = None


class Task(BaseModel):
    task_id: str
    steps: list[Step]


class PermissionToken(BaseModel):
    task_id: str
    granted_scopes: list[str]


class ToolResult(BaseModel):
    step_id: str
    tool_name: str
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None


class AuditEntry(BaseModel):
    task_id: str
    step_id: str
    tool_name: str
    scope_used: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat() + "Z")
    status: str
    error: str | None = None
