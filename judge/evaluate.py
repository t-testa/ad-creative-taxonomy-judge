"""Measure the parser against the ground truth the generator wrote.

The question that matters for trust is not only "how many names did we
decode" but "when we said we were sure, how often were we wrong". An ad
that is decoded wrongly and silently counted is worse than one sent to
review, so confidently-wrong parses are reported on their own line.
"""
import pandas as pd


def evaluate(decoded: pd.DataFrame, truth: pd.DataFrame, fields) -> dict:
    t = truth.set_index("ad_id")
    d = decoded.set_index("ad_id")
    auto = d[d["parse_status"] == "AUTO"]
    field_acc, wrong_ids = {}, set()
    for f in fields:
        ok = auto[f].astype(str) == t.loc[auto.index, f].astype(str)
        field_acc[f] = round(100 * float(ok.mean()), 1)
        wrong_ids |= set(auto.index[~ok])
    review = d[d["parse_status"] == "REVIEW"]
    kinds = t.loc[review.index, "kind"].value_counts().to_dict()
    undecodable = t[t["kind"] != "normal"].index
    return {
        "ads": int(len(d)),
        "auto": int(len(auto)),
        "field_accuracy_pct": field_acc,
        "confidently_wrong": int(len(wrong_ids)),
        "review": int(len(review)),
        "review_by_cause": {k: int(v) for k, v in kinds.items()},
        "undecodable_names": int(len(undecodable)),
        "undecodable_caught_pct": round(100 * float(d.loc[undecodable, "parse_status"].ne("AUTO").mean()), 1)
        if len(undecodable) else None,
    }
