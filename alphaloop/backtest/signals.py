"""The strategy expression mini-language used by ``signals.entry/exit/score``.

A spec's ``signals.entry``, ``signals.exit``, and ``signals.score`` are
plain Python boolean/float expressions evaluated per-symbol against that
symbol's feature columns, e.g.::

    entry: "close > close.rolling(20).mean() and volume > volume.rolling(20).mean()"
    exit:  "close < close.rolling(20).mean()"
    score: "close.pct_change(24)"   # 24-period momentum, ranked across the universe

Feature columns are exposed under their short name (the part after the
last ``.``, e.g. ``price.ohlcv.close`` -> ``close``); on a collision the
full dotted name (with ``.`` replaced by ``_``) is also available. This
keeps expressions readable without hand-writing a real parser.

Evaluation uses ``pandas.eval``-style attribute access via a small
:class:`SeriesNamespace` rather than raw ``eval`` on the expression
string — arithmetic, comparisons, and boolean ``and``/``or``/``not`` on
Series all work through normal Python operator overloading, but no
builtins, imports, or attribute access beyond whitelisted Series methods
are reachable, so a hand-edited spec cannot execute arbitrary code.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

import pandas as pd

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_CMPOPS = {
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_ALLOWED_BOOLOPS = {ast.And: "and", ast.Or: "or"}
_ALLOWED_METHODS = {
    "rolling",
    "mean",
    "std",
    "sum",
    "min",
    "max",
    "pct_change",
    "shift",
    "diff",
    "abs",
    "ewm",
    "rank",
    "clip",
    "fillna",
}


class SignalExpressionError(ValueError):
    pass


def _safe_column_names(columns: list[str]) -> dict[str, str]:
    """Map both short and full-sanitized names to the real column name."""

    mapping: dict[str, str] = {}
    for col in columns:
        full = col.replace(".", "_").replace(":", "_")
        mapping[full] = col
        short = col.rsplit(".", 1)[-1]
        if short not in mapping:
            mapping[short] = col
        else:
            # ambiguous short name: only the full form is safe to use
            mapping.pop(short, None)
    return mapping


class _Evaluator(ast.NodeVisitor):
    """Walks a whitelisted AST subset, evaluating against a symbol's feature frame."""

    def __init__(self, frame: pd.DataFrame, name_map: dict[str, str]):
        self.frame = frame
        self.name_map = name_map

    def visit(self, node: ast.AST) -> Any:
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, None)
        if visitor is None:
            raise SignalExpressionError(
                f"unsupported expression element: {node.__class__.__name__}"
            )
        return visitor(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise SignalExpressionError(f"operator {node.op!r} not allowed")
        return op(self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if isinstance(node.op, ast.USub):
            return -self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return ~self.visit(node.operand)
        raise SignalExpressionError(f"unary operator {node.op!r} not allowed")

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            result = values[0]
            for v in values[1:]:
                result = result & v
            return result
        result = values[0]
        for v in values[1:]:
            result = result | v
        return result

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        result = None
        for op_node, comparator in zip(node.ops, node.comparators, strict=True):
            op = _ALLOWED_CMPOPS.get(type(op_node))
            if op is None:
                raise SignalExpressionError(f"comparison {op_node!r} not allowed")
            right = self.visit(comparator)
            clause = op(left, right)
            result = clause if result is None else (result & clause)
            left = right
        return result

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Attribute):
            raise SignalExpressionError("only method calls like x.rolling(20).mean() are allowed")
        if node.func.attr not in _ALLOWED_METHODS:
            raise SignalExpressionError(f"method {node.func.attr!r} is not whitelisted")
        target = self.visit(node.func.value)
        method = getattr(target, node.func.attr)
        args = [self.visit(a) for a in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords if kw.arg}
        return method(*args, **kwargs)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if node.attr not in _ALLOWED_METHODS:
            raise SignalExpressionError(f"attribute {node.attr!r} is not whitelisted")
        target = self.visit(node.value)
        return getattr(target, node.attr)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id not in self.name_map:
            raise SignalExpressionError(
                f"unknown identifier {node.id!r}; available: {sorted(self.name_map)}"
            )
        return self.frame[self.name_map[node.id]]

    def visit_Constant(self, node: ast.Constant) -> Any:
        if not isinstance(node.value, int | float | bool):
            raise SignalExpressionError(f"literal {node.value!r} not allowed")
        return node.value


def evaluate_signal(expr: str, frame: pd.DataFrame) -> pd.Series:
    """Evaluate a signal expression against one symbol's feature DataFrame."""

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise SignalExpressionError(f"invalid signal expression {expr!r}: {e}") from e
    name_map = _safe_column_names(list(frame.columns))
    result = _Evaluator(frame, name_map).visit(tree)
    if not isinstance(result, pd.Series):
        result = pd.Series(result, index=frame.index)
    return result
