from __future__ import annotations

import ast
import operator
from typing import Any

from .base import BaseTool


class SafeEval(ast.NodeVisitor):
    BINOPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
        ast.FloorDiv: operator.floordiv,
    }

    UNOPS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)
        if op_type not in self.BINOPS:
            raise ValueError(f"Unsupported binary operator: {op_type}")
        return self.BINOPS[op_type](left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        op_type = type(node.op)
        if op_type not in self.UNOPS:
            raise ValueError(f"Unsupported unary operator: {op_type}")
        return self.UNOPS[op_type](operand)

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, (ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp)):
            return super().visit(node)
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    evaluator = SafeEval()
    return evaluator.visit(tree)


class MockCalculatorTool(BaseTool):
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        expression = input_data.get("expression", "0")
        try:
            result = safe_eval(expression)
            return {"expression": expression, "result": float(result)}
        except Exception as e:
            raise ValueError(f"Invalid expression: {e}") from e