"""Safe arithmetic evaluation."""

from __future__ import annotations

import ast
import math


class ArithmeticError(ValueError):
    pass


def evaluate(expression: str) -> float:
    if not expression or not expression.strip():
        raise ArithmeticError("empty expression")
    if len(expression) > 256:
        raise ArithmeticError("expression is too long")

    try:
        root = ast.parse(expression, mode="eval").body
    except SyntaxError as exc:
        raise ArithmeticError(f"invalid syntax: {exc.msg}") from exc

    return _eval_node(root)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_node(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            result = left / right
        elif isinstance(node.op, ast.FloorDiv):
            result = left // right
        elif isinstance(node.op, ast.Mod):
            result = left % right
        elif isinstance(node.op, ast.Pow):
            if abs(right) > 12:
                raise ArithmeticError("exponent outside supported range")
            result = left ** right
        else:
            raise ArithmeticError("unsupported operator")
        if not isinstance(result, (int, float)) or not math.isfinite(result):
            raise ArithmeticError("result is not a finite real number")
        if abs(result) > 1e100:
            raise ArithmeticError("result outside supported range")
        return float(result)
    raise ArithmeticError("only basic arithmetic is supported")


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    return a / b