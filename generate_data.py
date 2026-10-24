"""Generate synthetic ad-platform exports for two fictional brands.

Each brand names its ads its own way, and real teams are inconsistent:
mixed separators, casing, abbreviations, typos, "COPY" suffixes, and a few
names nobody could decode. The true taxonomy of every ad is written to
data/ground_truth.csv, which the pipeline never reads. Only the eval uses
it, to measure how often the parser is right.

Performance has real signal baked in (some hooks, formats and creators work
better than others), so the insights the pipeline finds are checkable.
"""
import csv
import random
from pathlib import Path

import numpy as np

SEED = 7
RAW = Path("data/raw")

# ---------------------------------------------------------------- Northpeak
NP_FORMAT = {"UGC": (["UGC", "ugc", "User Generated"], 1.25, 1.15),
             "STATIC": (["Static", "IMG", "Image"], 0.85, None),
             "CAROUSEL": (["Carousel", "Carou"], 1.00, None),
             "STUDIO": (["Studio", "Prod", "Production"], 0.80, 0.85)}
NP_HOOK = {"PAIN_POINT": (["PainPoint", "Pain Point", "PP"], 1.30, 1.20),
           "SOCIAL_PROOF": (["SocialProof", "SP", "Reviews"], 1.10, 1.00),
           "OFFER": (["Offer", "Sale", "Promo"], 0.95, 0.90),
           "BEFORE_AFTER": (["BeforeAfter", "BA", "Before After"], 1.15, 1.10)}
NP_CREATOR = {"SARAH": (["Sarah"], 1.20), "MARCUS": (["Marcus"], 0.88),
              "PRIYA": (["Priya"], 1.05), "IN_HOUSE": (["InHouse", "In House", "Brand Team"], 0.85)}

# ---------------------------------------------------------------- Kindred
KG_CREATOR = {"JEN": (["Jen", "Jennifer"], 0.85), "ALEX": (["Alex"], 1.10),
              "MAYA": (["Maya"], 0.95), "NO_CREATOR": (["No Creator", "None"], 1.15)}
KG_HOOK = {"FOUNDER_STORY": (["Founder Story", "FounderStory", "Founder"], 0.80),
           "INGREDIENT": (["Ingredient", "Ingredients", "Ingr"], 1.05),
           "MORNING_ROUTINE": (["Morning Routine", "Routine"], 0.92),
           "TASTE_TEST": (["Taste Test", "TasteTest", "Taste"], 1.20)}
KG_FORMAT = {"TALKING_HEAD": (["Talking Head", "TH"], 0.95, 1.05),
             "DEMO": (["Demo", "Product Demo"], 1.00, 1.00),
             "TESTIMONIAL": (["Testimonial", "Testi"], 0.88, 1.10),
             "MEME": (["Meme", "Trend"], 1.15, 0.85)}
KG_LENGTH = {"15S": "15s", "30S": "30s", "60S": "60s"}
MONTHS = ["2026-08", "2026-09", "Sept", "SEP26", "Oct26", "2026-10"]

MANGLED = ["new video final", "test ad FINAL v2", "Copy of Copy of ad", "boosted post",
           "winner relaunch", "untitled 3", "q3 retarget"]


def typo(rng, token):
    if len(token) < 5:
        return token
    i = rng.randrange(1, len(token) - 1)
    return token[:i] + token[i + 1:] if rng.random() < 0.5 else token[:i] + token[i + 1] + token[i] + token[i + 2:]


UNSEEN = {"PainPoint": "PainPt", "SocialProof": "SoclProof", "BeforeAfter": "B4After", "Marcus": "Marc",
          "Carousel": "Carsl", "InHouse": "Internal", "Testimonial": "Tstml", "Ingredient": "Ingrdnt",
          "Taste Test": "TasteTst", "Talking Head": "Talkng Head", "Founder Story": "FndrStory", "Maya": "Mya"}


def messy(rng, tokens, seps):
    """Apply the inconsistencies real teams introduce when naming ads by hand."""
    if rng.random() < 0.10:                 # a spelling the brand config has never seen
        hits = [j for j, t in enumerate(tokens) if t in UNSEEN]
        if hits:
            j = rng.choice(hits)
            tokens[j] = UNSEEN[tokens[j]]
    if rng.random() < 0.14:
        j = rng.randrange(len(tokens))
        tokens[j] = typo(rng, tokens[j])
    name = rng.choice(seps).join(tokens)
    r = rng.random()
    name = name.lower() if r < 0.25 else name.upper() if r < 0.33 else name
    if rng.random() < 0.08:
        name += rng.choice([" - Copy", "_COPY", " dup", "_0915"])
    return name


def northpeak(rng, nrng, n=140):
    rows, truth = [], []
    for i in range(n):
        f, h, c = rng.choice(list(NP_FORMAT)), rng.choice(list(NP_HOOK)), rng.choice(list(NP_CREATOR))
        v = rng.randint(1, 6)
        tokens = [rng.choice(NP_FORMAT[f][0]) if rng.random() < 0.3 else NP_FORMAT[f][0][0],
                  rng.choice(NP_HOOK[h][0]) if rng.random() < 0.3 else NP_HOOK[h][0][0],
                  rng.choice(NP_CREATOR[c][0]) if rng.random() < 0.3 else NP_CREATOR[c][0][0],
                  rng.choice([f"v{v}", f"V{v}", f"v0{v}"])]
        kind = "normal"
        if rng.random() < 0.05:
            name, kind = rng.choice(MANGLED), "mangled"
        elif rng.random() < 0.03:
            other = rng.choice([x for x in NP_HOOK if x != h])
            tokens[1] = f"{NP_HOOK[h][0][0]}+{NP_HOOK[other][0][0]}"
            name, kind = "_".join(tokens), "ambiguous"
        else:
            name = messy(rng, tokens, ["_", "_", "_", "-", " "])

        spend = float(np.round(nrng.lognormal(7.1, 0.8), 2))
        cpm = nrng.normal(14, 2.5)
        impressions = int(spend / max(cpm, 6) * 1000)
        video = NP_FORMAT[f][2] is not None
        hook_rate = float(np.clip(0.22 * NP_FORMAT[f][2] * NP_HOOK[h][2] * nrng.lognormal(0, 0.15), 0.05, 0.6)) if video else 0
        ctr = float(np.clip(0.011 * NP_HOOK[h][1] * nrng.lognormal(0, 0.2), 0.002, 0.05))
        roas = 2.3 * NP_FORMAT[f][1] * NP_HOOK[h][1] * NP_CREATOR[c][1] * nrng.lognormal(0, 0.22)
        revenue = round(spend * roas, 2)
        rows.append({"Ad ID": f"NP{23800000 + i}", "Ad name": name, "Amount spent (CAD)": spend,
                     "Impressions": impressions, "Link clicks": int(impressions * ctr),
                     "3-second video plays": int(impressions * hook_rate), "Purchases": max(0, round(revenue / 86)),
                     "Purchases conversion value": revenue})
        truth.append({"brand": "northpeak", "ad_id": f"NP{23800000 + i}", "kind": kind,
                      "format": f, "hook": h, "creator": c, "length": ""})
    return {"northpeak_meta.csv": rows}, truth


def kindred(rng, nrng, n=110):
    files, truth = {"kindred_meta.csv": [], "kindred_tiktok.csv": []}, []
    for i in range(n):
        c, h, f = rng.choice(list(KG_CREATOR)), rng.choice(list(KG_HOOK)), rng.choice(list(KG_FORMAT))
        ln = rng.choice(list(KG_LENGTH))
        tokens = [rng.choice(MONTHS),
                  rng.choice(KG_CREATOR[c][0]) if rng.random() < 0.3 else KG_CREATOR[c][0][0],
                  rng.choice(KG_HOOK[h][0]) if rng.random() < 0.3 else KG_HOOK[h][0][0],
                  rng.choice(KG_FORMAT[f][0]) if rng.random() < 0.3 else KG_FORMAT[f][0][0],
                  KG_LENGTH[ln]]
        kind = "normal"
        if rng.random() < 0.05:
            name, kind = rng.choice(MANGLED), "mangled"
        elif rng.random() < 0.03:
            other = rng.choice([x for x in KG_FORMAT if x != f])
            tokens[3] = f"{KG_FORMAT[f][0][0]} or {KG_FORMAT[other][0][0]}"
            name, kind = " | ".join(tokens), "ambiguous"
        else:
            name = messy(rng, tokens, [" | ", " | ", " / ", "_", " - "])

        tiktok = rng.random() < 0.45
        spend = float(np.round(nrng.lognormal(6.7, 0.85), 2))
        impressions = int(spend / max(nrng.normal(9 if tiktok else 13, 2), 4) * 1000)
        ctr = float(np.clip(0.012 * KG_FORMAT[f][2] * nrng.lognormal(0, 0.2), 0.002, 0.05))
        cpa = 41 * KG_CREATOR[c][1] ** -1 * KG_HOOK[h][1] ** -1 * KG_FORMAT[f][1] ** -1 * nrng.lognormal(0, 0.2)
        purchases = int(spend / cpa)
        row = [f"KG{51200000 + i}", name, spend, impressions, int(impressions * ctr),
               int(impressions * float(np.clip(nrng.normal(0.27, 0.05), 0.08, 0.5))), purchases, round(purchases * 54.0, 2)]
        if tiktok:
            keys = ["Ad ID", "Ad Name", "Cost", "Impressions", "Clicks (Destination)", "Video Views at 3s",
                    "Complete Payment", "Total Complete Payment Value"]
            files["kindred_tiktok.csv"].append(dict(zip(keys, row)))
        else:
            keys = ["Ad ID", "Ad name", "Amount spent (CAD)", "Impressions", "Link clicks", "3-second video plays",
                    "Purchases", "Purchases conversion value"]
            files["kindred_meta.csv"].append(dict(zip(keys, row)))
        truth.append({"brand": "kindred", "ad_id": f"KG{51200000 + i}", "kind": kind,
                      "format": f, "hook": h, "creator": c, "length": ln})
    return files, truth


def write(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    rng, nrng = random.Random(SEED), np.random.default_rng(SEED)
    RAW.mkdir(parents=True, exist_ok=True)
    truth = []
    for gen in (northpeak, kindred):
        files, t = gen(rng, nrng)
        truth += t
        for name, rows in files.items():
            write(RAW / name, rows)
    write(Path("data/ground_truth.csv"), truth)
    print(f"wrote {len(truth)} ads across {len(list(RAW.glob('*.csv')))} exports")
