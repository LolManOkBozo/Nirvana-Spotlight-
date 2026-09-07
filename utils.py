"""
Utility functions for Winspot
"""
import ast
import operator
import re

# Safe math operations mapping
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def safe_eval(expr: str):
    """Safely evaluate mathematical expressions"""
    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_eval(node.operand))
        raise ValueError("unsupported expression")

    tree = ast.parse(expr, mode="eval")
    return _eval(tree.body)

def looks_like_math(text: str) -> bool:
    """Check if text looks like a mathematical expression"""
    return bool(re.fullmatch(r"[0-9\.\s\+\-\*\/\%\(\)\^]+", text)) and any(c.isdigit() for c in text)
