"""Load a brand's exports, decode every ad name, judge every ad, and
summarize what is driving performance. Every figure that reaches the memo or
the dashboard comes from the metrics dict returned here."""
from pathlib import Path

import pandas as pd

from .llm import build_prompt, validate
from .rules import judge, load_rules
from difflib import SequenceMatcher

from .taxonomy import Brand, key, parse_name

LOWER_IS_BETTER = {"cpa"}


def load_exports(brand: Brand, raw_dir: Path) -> pd.DataFrame:
    frames = []
    for exp in brand.exports:
        df = pd.read_csv(raw_dir / exp["file"], dtype={"Ad ID": str}).rename(columns=exp["columns"])
        df["platform"] = exp["platform"]
        frames.append(df[list(exp["columns"].values()) + ["platform"]])
    df = pd.concat(frames, ignore_index=True)
    df["roas"] = (df["revenue"] / df["spend"]).round(3)
    df["cpa"] = (df["spend"] / df["purchases"].where(df["purchases"] > 0)).round(2)
    df["ctr"] = (df["clicks"] / df["impressions"]).round(4)
    df["cvr"] = (df["purchases"] / df["clicks"].where(df["clicks"] > 0)).round(4)
    df["is_video"] = df["video_3s"] > 0
    df["hook_rate"] = (df["video_3s"] / df["impressions"]).where(df["is_video"]).round(3)
    return df


def suggest(p, brand: Brand):
    """When exactly one required field is missing and one unknown token is left,
    that token is probably a new spelling for the field. Propose it as a
    one-line config addition; a person accepts or rejects it."""
    missing = [f for f in brand.required if f not in p.values]
    if p.status != "REVIEW" or len(missing) != 1 or len(p.leftover) != 1:
        return None
    tok, fld = p.leftover[0], missing[0]
    close = max(((SequenceMatcher(None, tok, key(str(s))).ratio(), canon)
                 for canon, syns in brand.fields[fld].items() for s in [canon] + list(syns)), default=(0, None))
    if close[0] >= 0.6:
        return f"'{tok}' looks like {fld} {close[1]}: fix the name or add it as a spelling"
    return f"'{tok}' is a new {fld} spelling: map it to a {fld} value in taxonomy.yaml"


def decode(df: pd.DataFrame, brand: Brand, llm=None) -> pd.DataFrame:
    out = []
    for name in df["ad_name"]:
        p = parse_name(name, brand)
        if p.status == "REVIEW" and llm is not None:
            p = validate(llm(build_prompt(name, brand)), brand)
        out.append({**{f: p.values.get(f) for f in list(brand.fields) + list(brand.patterns)},
                    "parse_status": p.status, "parse_confidence": p.confidence,
                    "parse_reason": p.reason, "parse_source": p.source,
                    "suggestion": suggest(p, brand)})
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(out)], axis=1)


def apply_rules(df: pd.DataFrame, rules_path: Path) -> pd.DataFrame:
    rules = load_rules(rules_path)
    verdicts = [judge({k: (None if pd.isna(v) else v) for k, v in r.items()}, rules)
                for r in df.to_dict("records")]
    df["verdict"], df["verdict_reason"] = zip(*verdicts)
    return df


def _agg(g: pd.DataFrame) -> dict:
    spend, rev, purch = g["spend"].sum(), g["revenue"].sum(), g["purchases"].sum()
    return {"ads": int(len(g)), "spend": round(float(spend), 2),
            "roas": round(float(rev / spend), 2) if spend else None,
            "cpa": round(float(spend / purch), 2) if purch else None,
            "scale_ads": int((g["verdict"] == "SCALE").sum())}


def summarize(df: pd.DataFrame, brand: Brand) -> dict:
    pm = brand.primary_metric
    trusted = df[df["parse_status"].isin(["AUTO", "LLM"])]
    total = _agg(df)
    by_field, drivers = {}, []
    for fld in brand.required:
        rows = []
        for val, g in trusted.groupby(fld):
            a = _agg(g)
            a["value"] = val
            a["spend_share_pct"] = round(100 * a["spend"] / total["spend"], 1)
            rows.append(a)
        rows = [r for r in rows if r[pm] is not None]
        rows.sort(key=lambda r: r[pm], reverse=pm not in LOWER_IS_BETTER)
        by_field[fld] = rows
        if len(rows) >= 2:
            best, worst = rows[0], rows[-1]
            gap = (worst[pm] / best[pm] - 1) if pm in LOWER_IS_BETTER else (best[pm] / worst[pm] - 1)
            drivers.append({"field": fld, "best": best["value"], "best_value": best[pm],
                            "worst": worst["value"], "worst_value": worst[pm],
                            "gap_pct": round(100 * gap, 1)})
    drivers.sort(key=lambda d: d["gap_pct"], reverse=True)

    combos = []
    a, b = brand.required[0], brand.required[1]
    for (va, vb), g in trusted.groupby([a, b]):
        if len(g) >= 3:
            c = _agg(g)
            if c[pm] is not None:
                combos.append({a: va, b: vb, **c})
    combos.sort(key=lambda r: r[pm], reverse=pm not in LOWER_IS_BETTER)

    verdicts = df["verdict"].value_counts().to_dict()
    kill = df[df["verdict"] == "KILL"]
    review = df[df["parse_status"] == "REVIEW"]
    return {
        "brand": brand.name, "slug": brand.slug, "primary_metric": pm,
        "platforms": sorted(df["platform"].unique().tolist()),
        "total": total,
        "parsing": {"ads": int(len(df)), "auto": int((df["parse_status"] == "AUTO").sum()),
                    "llm": int((df["parse_status"] == "LLM").sum()), "review": int(len(review)),
                    "typo_corrected": int((df["parse_reason"] == "typo corrected").sum()),
                    "auto_pct": round(100 * (df["parse_status"] == "AUTO").mean(), 1),
                    "review_spend": round(float(review["spend"].sum()), 2),
                    "suggested_fixes": int(review["suggestion"].notna().sum())},
        "verdicts": {k: int(verdicts.get(k, 0)) for k in ["SCALE", "ITERATE", "KILL", "TOO_EARLY"]},
        "kill_spend": round(float(kill["spend"].sum()), 2),
        "kill_spend_pct": round(100 * float(kill["spend"].sum()) / total["spend"], 1),
        "by_field": by_field, "drivers": drivers, "top_combos": combos[:3], "bottom_combos": combos[-2:],
    }


def run_brand(folder: Path, raw_dir: Path, llm=None):
    brand = Brand.load(folder)
    df = apply_rules(decode(load_exports(brand, raw_dir), brand, llm), folder / "rules.csv")
    return brand, df, summarize(df, brand)
