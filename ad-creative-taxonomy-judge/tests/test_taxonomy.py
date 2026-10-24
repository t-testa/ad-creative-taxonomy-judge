from pathlib import Path

from judge.pipeline import suggest
from judge.taxonomy import Brand, parse_name

NP = Brand.load(Path("brands/northpeak"))
KG = Brand.load(Path("brands/kindred"))


def test_exact_parse_any_separator_and_case():
    for name in ["UGC_PainPoint_Sarah_v3", "ugc-pain point-sarah-V03", "UGC PP SARAH v3 - Copy"]:
        p = parse_name(name, NP)
        assert p.status == "AUTO"
        assert p.values["format"] == "UGC" and p.values["hook"] == "PAIN_POINT" and p.values["creator"] == "SARAH"
        assert p.values["version"] == "3"


def test_typo_is_corrected_with_lower_confidence():
    p = parse_name("UGC_SocialProf_Priya_v2", NP)
    assert p.status == "AUTO" and p.values["hook"] == "SOCIAL_PROOF"
    assert p.confidence == 0.8 and p.reason == "typo corrected"


def test_two_values_for_one_field_goes_to_review():
    p = parse_name("UGC_PainPoint+Offer_Sarah_v1", NP)
    assert p.status == "REVIEW" and "conflicting values for hook" in p.reason


def test_undecodable_name_goes_to_review_not_guessed():
    p = parse_name("new video final", NP)
    assert p.status == "REVIEW" and p.values == {}


def test_other_brand_convention_parses_with_its_own_config():
    p = parse_name("2026-09 | Jen | Founder Story | Talking Head | 15s", KG)
    assert p.status == "AUTO"
    assert p.values == {"creator": "JEN", "hook": "FOUNDER_STORY", "format": "TALKING_HEAD", "length": "15S"}


def test_unseen_spelling_produces_a_config_suggestion():
    p = parse_name("UGC_PainPoint_Internal_v2", NP)
    assert p.status == "REVIEW" and p.leftover == ["internal"]
    assert "new creator spelling" in suggest(p, NP)
    p = parse_name("Staitc_PainPoint_Marcus_v1", NP)
    assert "looks like format STATIC" in suggest(p, NP)
