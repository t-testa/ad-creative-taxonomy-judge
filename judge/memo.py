"""Write the weekly "what's winning and why" memo for a brand.

With ANTHROPIC_API_KEY set, Claude drafts the memo from metrics.json using
prompts/weekly_memo.md. Without a key, a deterministic template writes it.
Either way the grounding check runs before the memo is saved, and a memo
with any figure that does not trace back to the metrics is rejected.
"""
import json
import os
from pathlib import Path

from .grounding import check

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "weekly_memo.md"


ACRONYMS = {"UGC"}


def label(v) -> str:
    v = str(v)
    return v if v in ACRONYMS else v.replace("_", " ").title()


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def money(v: float) -> str:
    return f"${v / 1e3:.1f}K" if v >= 1e3 else f"${v:,.0f}"


def fmt(metric: str, v: float) -> str:
    return f"{v:.2f}x ROAS" if metric == "roas" else f"${v:.2f} CPA"


def template_memo(m: dict) -> str:
    pm, p, v = m["primary_metric"], m["parsing"], m["verdicts"]
    d0 = m["drivers"][0]
    lines = [f"# Weekly creative read: {m['brand']}", "",
             f"**{cap(label(d0['best']))} is the clearest winner this period: {fmt(pm, d0['best_value'])} "
             f"against {fmt(pm, d0['worst_value'])} for {label(d0['worst'])}, a {d0['gap_pct']}% gap on the "
             f"{label(d0['field']).lower()} dimension.**", "", "## What is driving performance", ""]
    for d in m["drivers"][:3]:
        lines.append(f"- **{label(d['field']).capitalize()}:** {label(d['best'])} leads at {fmt(pm, d['best_value'])}; "
                     f"{label(d['worst'])} trails at {fmt(pm, d['worst_value'])} ({d['gap_pct']}% gap).")
    if m["top_combos"]:
        c = m["top_combos"][0]
        a, b = [k for k in c if k not in {"ads", "spend", "roas", "cpa", "scale_ads"}][:2]
        lines.append(f"- **Best combination:** {label(c[a])} with {label(c[b])}, {c['ads']} ads at {fmt(pm, c[pm])}.")
    lines += ["", "## What to do this week", "",
              f"- **Scale** the {v['SCALE']} ads that clear the brand's scale bar.",
              f"- **Cut** the {v['KILL']} ads below the line: {money(m['kill_spend'])} of spend, "
              f"{m['kill_spend_pct']}% of the total.",
              f"- **Iterate** on the {v['ITERATE']} ads in the middle band, and leave the {v['TOO_EARLY']} "
              "ads without enough data running before judging them."]
    if m["top_combos"]:
        lines.append(f"- **Brief the next round** around {label(c[a])} plus {label(c[b])}.")
    lines += ["", "## Data quality", "",
              f"- {p['auto']} of {p['ads']} ad names decoded automatically ({p['auto_pct']}%), including "
              f"{p['typo_corrected']} with typos corrected.",
              f"- {p['review']} ads ({money(p['review_spend'])} of spend) could not be decoded with confidence and are "
              "excluded from the breakdowns above until the names are fixed. They are listed in the review queue, "
              f"with {p['suggested_fixes']} one-line naming fixes already suggested."]
    return "\n".join(lines) + "\n"


def claude_memo(m: dict):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    prompt = PROMPT.read_text().replace("{{METRICS}}", json.dumps(m, indent=2))
    msg = anthropic.Anthropic().messages.create(model="claude-sonnet-4-5", max_tokens=900, temperature=0,
                                                messages=[{"role": "user", "content": prompt}])
    return msg.content[0].text


def write_memo(m: dict) -> tuple:
    """Return (memo_text, source, grounding_result). Falls back to the template
    if the model's draft contains any ungrounded figure."""
    draft = claude_memo(m)
    if draft is not None:
        g = check(draft, m)
        if not g["ungrounded"]:
            return draft, "claude", g
    memo = template_memo(m)
    g = check(memo, m)
    if g["ungrounded"]:
        raise ValueError(f"template memo has ungrounded figures: {g['ungrounded']}")
    return memo, "template", g
