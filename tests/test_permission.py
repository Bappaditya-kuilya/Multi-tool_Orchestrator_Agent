import pytest

from src.models import PermissionToken, Task, Step
from src.permission import PermissionScoper


def test_token_creation(scoper, sample_task):
    token = scoper.issue_token(sample_task)
    assert isinstance(token, PermissionToken)
    assert token.task_id == "test-1"
    assert "calculator:eval" in token.granted_scopes
    assert "weather:read" in token.granted_scopes


def test_scope_check_pass(scoper, sample_task):
    token = scoper.issue_token(sample_task)
    assert scoper.check_scope("calculator:eval", token)
    assert scoper.check_scope("weather:read", token)


def test_scope_check_fail(scoper, sample_task):
    token = scoper.issue_token(sample_task)
    assert not scoper.check_scope("admin:delete", token)