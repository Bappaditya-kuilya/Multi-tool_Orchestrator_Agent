from __future__ import annotations

import ast
import math
from typing import Any

from .base import BaseTool
from .mock_calculator import SafeEval


class AdvancedSafeEval(SafeEval):
    FUNCS = {
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
    }

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name) or node.func.id not in self.FUNCS:
            raise ValueError(f"Unsupported function call: {ast.dump(node.func)}")
        if node.keywords:
            raise ValueError("Keyword arguments not supported")
        args = [self.visit(arg) for arg in node.args]
        result = self.FUNCS[node.func.id](*args)
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("Result out of range")
        return result

    def visit_Name(self, node: ast.Name) -> Any:
        raise ValueError(f"Unsupported name: {node.id}")

    def visit(self, node: ast.AST) -> Any:
        if isinstance(
            node,
            (ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp, ast.Call, ast.Name),
        ):
            # F-6: dispatch must cover Call/Name or visit_Call/visit_Name never run
            # skip SafeEval.visit (its own allowlist) and hit the generic dispatcher
            return ast.NodeVisitor.visit(self, node)
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def advanced_safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    evaluator = AdvancedSafeEval()
    return evaluator.visit(tree)


class MockCalculatorAdvancedTool(BaseTool):
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        expression = input_data.get("expression", "0")
        try:
            result = advanced_safe_eval(expression)
            return {"expression": expression, "result": float(result)}
        except Exception as e:
            raise ValueError(f"Invalid expression: {e}") from e
