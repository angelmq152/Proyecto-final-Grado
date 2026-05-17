import ast
import operator
from collections.abc import Callable
from datetime import UTC, datetime

_ALLOWED_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_ALLOWED_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def get_time() -> dict[str, str]:
    return {"now": datetime.now(UTC).isoformat()}


def echo(text: str) -> dict[str, str]:
    return {"echoed": text}


def simple_calc(expr: str) -> dict[str, float]:
    tree = ast.parse(expr, mode="eval")
    result = _eval_node(tree.body)
    return {"result": float(result)}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)

    if isinstance(node, ast.BinOp):
        bin_op_type = type(node.op)
        if bin_op_type not in _ALLOWED_BIN_OPS:
            raise ValueError(f"Operator not allowed: {bin_op_type.__name__}")
        return float(_ALLOWED_BIN_OPS[bin_op_type](_eval_node(node.left), _eval_node(node.right)))

    if isinstance(node, ast.UnaryOp):
        unary_op_type = type(node.op)
        if unary_op_type not in _ALLOWED_UNARY_OPS:
            raise ValueError(f"Operator not allowed: {unary_op_type.__name__}")
        return float(_ALLOWED_UNARY_OPS[unary_op_type](_eval_node(node.operand)))

    raise ValueError(f"Expression not allowed: {type(node).__name__}")
