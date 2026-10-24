"""Run the full pipeline for every brand folder under brands/.

    python run.py                 # all brands
    python run.py --brand kindred # one brand

Outputs per brand, in output/<brand>/: decoded and judged ads, the review
queue, metrics.json, and the weekly memo. output/eval.json holds parser
accuracy against the synthetic ground truth.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from judge.evaluate import evaluate
from judge.llm import make_client
from judge.memo import write_memo
from judge.pipeline import run_brand

BRANDS, RAW, OUT = Path("brands"), Path("data/raw"), Path("output")


def main(only=None):
    llm = make_client()
    truth = pd.read_csv("data/ground_truth.csv", dtype=str).fillna("")
    evals = {}
    for folder in sorted(p for p in BRANDS.iterdir() if p.is_dir()):
        if only and folder.name != only:
            continue
        brand, df, m = run_brand(folder, RAW, llm)
        out = OUT / brand.slug
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "ads.csv", index=False)
        df[df["parse_status"] == "REVIEW"][["ad_id", "platform", "ad_name", "spend", "parse_reason", "suggestion"]] \
            .sort_values("spend", ascending=False).to_csv(out / "review_queue.csv", index=False)
        memo, source, g = write_memo(m)
        m["memo"] = {"source": source, "figures_checked": g["checked"], "ungrounded": len(g["ungrounded"])}
        (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
        (out / "memo.md").write_text(memo)
        evals[brand.slug] = evaluate(df, truth[truth["brand"] == brand.slug], brand.required)
        p, v = m["parsing"], m["verdicts"]
        print(f"{brand.name}: {p['ads']} ads, {p['auto']} decoded, {p['review']} to review | "
              f"scale {v['SCALE']}, iterate {v['ITERATE']}, kill {v['KILL']}, too early {v['TOO_EARLY']} | "
              f"memo ({source}): {g['checked']} figures, {len(g['ungrounded'])} ungrounded")
    (OUT / "eval.json").write_text(json.dumps(evals, indent=2))
    for slug, e in evals.items():
        print(f"eval {slug}: field accuracy {e['field_accuracy_pct']}, confidently wrong {e['confidently_wrong']}, "
              f"undecodable names caught {e['undecodable_caught_pct']}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand")
    main(ap.parse_args().brand)
