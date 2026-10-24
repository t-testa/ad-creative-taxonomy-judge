"""Judge each ad the way the brand does, from the brand's own rules sheet.

rules.csv is the kind of spreadsheet a growth team already keeps: ordered
rows of "if this condition, then this verdict, because this reason". The
first matching row wins. Conditions are evaluated with a small whitelist
parser (comparisons, and/or/not, numbers, known metric names) rather than
Python eval, so a customer-edited sheet cannot run arbitrary code.
"""
import ast
import csv
import operator
from pathlib import Path

METRICS = {"spend", "impressions", "clicks", "purchases", "revenue", "roas", "cpa", "ctr",
           "hook_rate", "cvr", "is_video"}
CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
       ast.Eq: operator.eq, ast.NotEq: operator.ne}


class RuleError(ValueError):
    pass


def _check(node):
    if isinstance(node, ast.Expression):
        return _check(node.body)
    if isinstance(node, ast.BoolOp):
        return all(_check(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _check(node.operand)
    if isinstance(node, ast.Compare):
        return all(type(op) in CMP for op in node.ops) and _check(node.left) and all(_check(c) for c in node.comparators)
    if isinstance(node, ast.Name):
        if node.id not in METRICS:
            raise RuleError(f"unknown metric '{node.id}'")
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
        return True
    raise RuleError(f"unsupported expression: {ast.dump(node)[:60]}")


def _eval(node, row):
    if isinstance(node, ast.Expression):
        return _eval(node.body, row)
    if isinstance(node, ast.BoolOp):
        vals = (_eval(v, row) for v in node.values)
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp):
        return not _eval(node.operand, row)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, row)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, row)
            if left is None or right is None or not CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        return row.get(node.id)
    return node.value


def load_rules(path: Path):
    rules = []
    with open(path) as fh:
        for r in sorted(csv.DictReader(fh), key=lambda r: int(r["order"])):
            tree = ast.parse(r["condition"], mode="eval")
            _check(tree)
            rules.append((r["verdict"], tree, r["reason"], r["condition"]))
    if not rules or rules[-1][3].strip() != "True":
        raise RuleError("the last rule must be a catch-all with condition True")
    return rules


def judge(row: dict, rules) -> tuple:
    for verdict, tree, reason, _ in rules:
        if _eval(tree, row):
            return verdict, reason
    raise RuleError("no rule matched")  # unreachable with a catch-all
