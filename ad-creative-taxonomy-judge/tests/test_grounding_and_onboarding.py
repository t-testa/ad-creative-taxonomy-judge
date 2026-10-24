import json
import shutil
from pathlib import Path

from judge.grounding import check
from judge.memo import template_memo
from judge.pipeline import run_brand


def test_memo_figures_all_trace_to_metrics():
    m = json.loads(Path("output/northpeak/metrics.json").read_text())
    assert check(template_memo(m), m)["ungrounded"] == []


def test_invented_figure_blocks_the_memo():
    m = json.loads(Path("output/northpeak/metrics.json").read_text())
    memo = template_memo(m) + "\nAlso, UGC drives a 312% lift in revenue.\n"
    assert "312%" in check(memo, m)["ungrounded"]


def test_new_brand_needs_config_only(tmp_path):
    """Onboarding a third brand is a folder with taxonomy.yaml, rules.csv and an export. No code."""
    brand = tmp_path / "brands" / "copperleaf"
    brand.mkdir(parents=True)
    (brand / "taxonomy.yaml").write_text("""
brand: Copperleaf Home
primary_metric: roas
exports:
  - file: copperleaf_meta.csv
    platform: Meta
    columns: {"Ad name": ad_name, "Ad ID": ad_id, "Amount spent (CAD)": spend, "Impressions": impressions,
              "Link clicks": clicks, "3-second video plays": video_3s, "Purchases": purchases,
              "Purchases conversion value": revenue}
required: [angle, format]
fields:
  angle: {GIFTING: [gift, gifting], COZY: [cozy, hygge]}
  format: {VIDEO: [vid, video], STATIC: [static]}
""")
    shutil.copy("brands/northpeak/rules.csv", brand / "rules.csv")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "copperleaf_meta.csv").write_text(
        "Ad ID,Ad name,Amount spent (CAD),Impressions,Link clicks,3-second video plays,Purchases,Purchases conversion value\n"
        "C1,Gift_Vid_01,800,50000,600,15000,30,3200\nC2,cozy-static,900,60000,500,0,12,1500\n"
        "C3,hygge VIDEO,700,40000,450,9000,20,2300\nC4,gifting_static_v2,650,42000,400,0,8,900\n")
    _, df, m = run_brand(brand, raw)
    assert list(df["parse_status"]) == ["AUTO"] * 4
    assert m["parsing"]["auto"] == 4 and m["by_field"]["angle"]
