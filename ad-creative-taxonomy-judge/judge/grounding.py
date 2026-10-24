"""Check that every figure in a memo traces back to the brand's metrics.

Each number is parsed with its unit ($, K, M, %, x) and the precision it
was written at, and passes only if some metric value rounds to it. Ad IDs
and version numbers are ignored. An invented figure blocks the memo.
"""
import json
import re
import sys

TOKEN = re.compile(r"\$?\d[\d,]*(?:\.\d+)?(?:\s?[KkMm]\b)?%?x?")
IGNORE = re.compile(r"\b(?:NP|KG)\d+\b|\bv\d+\b|\b20\d\d\b")


def _leaves(obj):
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _leaves(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v)


def parse(token: str):
    t = token.replace("$", "").replace(",", "").replace("%", "").rstrip("x").strip()
    mult = 1.0
    if t[-1:] in "KkMm":
        mult = 1e3 if t[-1] in "Kk" else 1e6
        t = t[:-1].strip()
    decimals = len(t.split(".")[1]) if "." in t else 0
    return float(t) * mult, 0.5 * (10 ** -decimals) * mult


def check(memo: str, metrics: dict) -> dict:
    vals = list(_leaves(metrics))
    text = IGNORE.sub(" ", memo)
    ungrounded, n = [], 0
    for m in TOKEN.finditer(text):
        value, tol = parse(m.group())
        n += 1
        if not any(abs(v - value) <= tol + 1e-9 for v in vals):
            ungrounded.append(m.group())
    return {"checked": n, "ungrounded": ungrounded}


if __name__ == "__main__":
    r = check(open(sys.argv[1]).read(), json.load(open(sys.argv[2])))
    print(f"{r['checked']} figures checked, {len(r['ungrounded'])} ungrounded: {r['ungrounded']}")
    sys.exit(1 if r["ungrounded"] else 0)
