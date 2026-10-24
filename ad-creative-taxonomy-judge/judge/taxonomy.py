"""Parse ad names into a brand's own taxonomy.

The brand config lists, for each field, the canonical values and every
spelling the team actually uses. Parsing is deterministic first:

1. Normalize the name (case, separators) and build 1- to 3-word grams.
2. Exact match against the brand's synonyms (confidence 1.0).
3. Fuzzy match for typos on longer tokens (confidence 0.8).
4. Two different values for one field, or a missing required field, means
   the parse is not trusted. It goes to the LLM fallback if one is
   configured, otherwise straight to a human review queue.

Nothing is guessed silently. Every parse carries a status and a reason.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import yaml

SEPARATORS = re.compile(r"[_\-|/+,.()\[\]]+")
FUZZY_MIN_LEN = 4
FUZZY_RATIO = 0.85
NOISE = re.compile(r"^(copy|dup|of|final|new|test|v\d+|\d+|20\d\d|sept?\d*|oct\d*|aug\d*)$")


def key(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


@dataclass
class Brand:
    slug: str
    name: str
    primary_metric: str
    min_confidence: float
    exports: list
    required: list
    fields: dict            # field -> {canonical value -> [synonyms]}
    patterns: dict = field(default_factory=dict)

    @classmethod
    def load(cls, folder: Path) -> "Brand":
        cfg = yaml.safe_load((folder / "taxonomy.yaml").read_text())
        return cls(slug=folder.name, name=cfg["brand"], primary_metric=cfg["primary_metric"],
                   min_confidence=cfg.get("min_confidence", 0.8), exports=cfg["exports"],
                   required=cfg["required"], fields={f: {str(k): v for k, v in vals.items()}
                                                     for f, vals in cfg["fields"].items()},
                   patterns=cfg.get("patterns", {}))

    def allowed(self, fld: str) -> set:
        return set(self.fields.get(fld, {}))


@dataclass
class Parse:
    values: dict
    confidence: float
    status: str          # AUTO, LLM, REVIEW
    reason: str
    source: str = "rules"
    leftover: list = field(default_factory=list)   # tokens nothing matched


def _grams(tokens):
    for n in (3, 2, 1):
        for i in range(len(tokens) - n + 1):
            yield i, n, "".join(tokens[i:i + n])


def parse_name(name: str, brand: Brand) -> Parse:
    tokens = [t for t in SEPARATORS.sub(" ", str(name).lower()).split() if t]
    lookup = {}
    for fld, vals in brand.fields.items():
        for canon, syns in vals.items():
            for s in [canon] + list(syns):
                lookup.setdefault(key(str(s)), []).append((fld, canon))

    used, found, conflicts = set(), {}, []

    def take(fld, canon, conf, span):
        if fld in found and found[fld][0] != canon:
            conflicts.append(fld)
        elif fld not in found or conf > found[fld][1]:
            found[fld] = (canon, conf)
        used.update(span)

    for i, n, g in _grams(tokens):                       # exact, longest first
        span = set(range(i, i + n))
        if span & used or g not in lookup:
            continue
        for fld, canon in lookup[g]:
            take(fld, canon, 1.0, span)

    for i, n, g in _grams(tokens):                       # fuzzy, for typos
        span = set(range(i, i + n))
        if n > 2 or span & used or len(g) < FUZZY_MIN_LEN:
            continue
        best = max(((SequenceMatcher(None, g, k).ratio(), k) for k in lookup if len(k) >= FUZZY_MIN_LEN),
                   default=(0, None))
        if best[0] >= FUZZY_RATIO:
            for fld, canon in lookup[best[1]]:
                if fld not in found:
                    take(fld, canon, 0.8, span)

    values = {f: v[0] for f, v in found.items()}
    for fld, pattern in brand.patterns.items():
        m = re.search(rf"\b{pattern}\b", " ".join(tokens))
        if m:
            values[fld] = m.group(1)

    leftover = [t for j, t in enumerate(tokens) if j not in used and not NOISE.match(t)]
    conf = min([found[f][1] for f in brand.required if f in found], default=0.0)
    if conflicts:
        return Parse(values, 0.0, "REVIEW", f"conflicting values for {', '.join(sorted(set(conflicts)))}", leftover=leftover)
    missing = [f for f in brand.required if f not in found]
    if missing:
        return Parse(values, 0.0, "REVIEW", f"missing {', '.join(missing)}", leftover=leftover)
    if conf < brand.min_confidence:
        return Parse(values, conf, "REVIEW", "low confidence match")
    note = "typo corrected" if conf < 1.0 else "exact match"
    return Parse(values, conf, "AUTO", note)
