from pathlib import Path

import pandas as pd
import pytest

from judge.llm import build_prompt, validate
from judge.pipeline import decode
from judge.rules import RuleError, judge, load_rules
from judge.taxonomy import Brand

NP = Brand.load(Path("brands/northpeak"))


def test_prompt_lists_only_allowed_values():
    prompt = build_prompt("winner relaunch", NP)
    assert "PAIN_POINT" in prompt and "unknown" in prompt


def test_llm_answer_outside_taxonomy_is_rejected():
    p = validate('{"format": "UGC", "hook": "CURIOSITY_GAP", "creator": "SARAH"}', NP)
    assert p.status == "REVIEW" and "hook=CURIOSITY_GAP" in p.reason


def test_llm_unknown_or_bad_json_goes_to_review():
    assert validate('{"format": "UGC", "hook": "unknown", "creator": "SARAH"}', NP).status == "REVIEW"
    assert validate("Sure! The format is UGC.", NP).status == "REVIEW"


def test_valid_llm_answer_is_accepted_but_flagged():
    df = pd.DataFrame({"ad_name": ["winner relaunch"]})
    fake = lambda prompt: '{"format": "UGC", "hook": "OFFER", "creator": "SARAH"}'
    out = decode(df, NP, llm=fake)
    assert out.loc[0, "parse_status"] == "LLM" and out.loc[0, "parse_source"] == "llm"
    assert out.loc[0, "hook"] == "OFFER"


def test_rules_first_match_wins_and_missing_metrics_never_match():
    rules = load_rules(Path("brands/northpeak/rules.csv"))
    assert judge({"spend": 100, "roas": 9.0, "hook_rate": 0.5, "is_video": True}, rules)[0] == "TOO_EARLY"
    assert judge({"spend": 900, "roas": 3.1, "hook_rate": 0.31, "is_video": True}, rules)[0] == "SCALE"
    assert judge({"spend": 900, "roas": 3.1, "hook_rate": None, "is_video": False}, rules)[0] == "SCALE"
    assert judge({"spend": 900, "roas": 1.2, "hook_rate": None, "is_video": False}, rules)[0] == "KILL"


def test_rules_sheet_cannot_run_code(tmp_path):
    bad = tmp_path / "rules.csv"
    bad.write_text("order,verdict,condition,reason\n1,SCALE,__import__('os').system('ls'),x\n2,KILL,True,y\n")
    with pytest.raises(RuleError):
        load_rules(bad)
    bad.write_text("order,verdict,condition,reason\n1,SCALE,profit > 3,x\n2,KILL,True,y\n")
    with pytest.raises(RuleError, match="unknown metric"):
        load_rules(bad)
