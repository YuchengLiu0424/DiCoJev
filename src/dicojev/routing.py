"""Conservative routing for deterministic requests that do not need a decision model."""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DirectAnswer:
    goal: str
    answer: str
    method: str
    confidence: float = 1.0


_PREFIX = re.compile(
    r"^\s*(?:calculate|compute|evaluate|what\s+is|what's)\s*:?[\s]*(.+?)\s*[?]?\s*$",
    re.IGNORECASE,
)
_BARE_EXPRESSION = re.compile(r"^[\d\s+\-*/%().]+$")
_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        if abs(node.value) > 10**100:
            raise ValueError("number is too large")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 12:
            raise ValueError("exponent is too large")
        result = _OPERATORS[type(node.op)](left, right)
        if not isinstance(result, int | float) or abs(result) > 10**100:
            raise ValueError("result is outside the safe calculation range")
        return result
    raise ValueError("unsupported calculation syntax")


def route_direct_answer(context: str) -> DirectAnswer | None:
    """Return a deterministic answer only for an unambiguous arithmetic request."""
    normalized = context.strip()
    match = _PREFIX.fullmatch(normalized)
    expression = match.group(1) if match else normalized
    if len(expression) > 100 or not _BARE_EXPRESSION.fullmatch(expression):
        return None
    try:
        tree = ast.parse(expression, mode="eval")
        value = _evaluate(tree)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None
    answer = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    return DirectAnswer(
        goal=f"Calculate {expression.strip()} accurately",
        answer=answer,
        method="deterministic calculator",
    )
