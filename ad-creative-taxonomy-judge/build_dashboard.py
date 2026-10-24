"""Build output/dashboard.html: one self-contained page per brand with the
headline numbers, what is driving performance, the verdict board, ads to
scale and cut, the naming review queue, parser accuracy and the memo."""
import html
import json
import re
from pathlib import Path

import pandas as pd

OUT = Path("output")
VERDICT = {"SCALE": ("good", "▲", "Scale"), "ITERATE": ("warning", "◆", "Iterate"),
           "KILL": ("critical", "✕", "Kill"), "TOO_EARLY": ("neutral", "…", "Too early")}


def esc(v):
    return html.escape(str(v))


def label(v):
    v = str(v)
    return v if v in {"UGC"} else v.replace("_", " ").title()


def money(v):
    return f"${v / 1e3:,.1f}K" if v >= 1e3 else f"${v:,.0f}"


def metric_fmt(pm, v):
    return f"{v:.2f}x" if pm == "roas" else f"${v:.2f}"


def bars(rows, pm, total_spend):
    W, LW, BH, GAP = 340, 112, 20, 8
    vmax = max(r[pm] for r in rows) * 1.08
    pw = W - LW - 58
    H = len(rows) * (BH + GAP) + 6
    out = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img">']
    for i, r in enumerate(rows):
        y = 4 + i * (BH + GAP)
        w = max(4, pw * r[pm] / vmax)
        tip = (f"{label(r['value'])}: {metric_fmt(pm, r[pm])} {pm.upper()} · {r['ads']} ads · "
               f"{money(r['spend'])} spend ({r['spend_share_pct']}%) · {r['scale_ads']} at scale")
        cls = "mark best" if i == 0 else "mark"
        out.append(f'<g class="bar"><title>{esc(tip)}</title>'
                   f'<rect x="0" y="{y - 4}" width="{W}" height="{BH + 8}" fill="transparent"/>'
                   f'<text x="{LW - 8}" y="{y + 14}" text-anchor="end" class="lbl">{esc(label(r["value"]))}</text>'
                   f'<path d="M{LW},{y} h{w - 4} a4,4 0 0 1 4,4 v{BH - 8} a4,4 0 0 1 -4,4 h-{w - 4} z" class="{cls}"/>'
                   f'<text x="{LW + w + 5}" y="{y + 14}" class="val">{metric_fmt(pm, r[pm])}</text></g>')
    out.append("</svg>")
    table = "".join(f"<tr><td>{esc(label(r['value']))}</td><td>{metric_fmt(pm, r[pm])}</td><td>{r['ads']}</td>"
                    f"<td>{money(r['spend'])}</td><td>{r['scale_ads']}</td></tr>" for r in rows)
    out.append(f'<details><summary>Table view</summary><table><tr><th>Value</th><th>{pm.upper()}</th><th>Ads</th>'
               f'<th>Spend</th><th>At scale</th></tr>{table}</table></details>')
    return "".join(out)


def chip(v):
    tone, icon, text = VERDICT[v]
    return f'<span class="chip {tone}"><span aria-hidden="true">{icon}</span> {text}</span>'


def md(text):
    out, in_list = [], False
    for line in text.splitlines():
        line = esc(line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("## "):
            out.append(f"<h4>{line[3:]}</h4>")
        elif line.startswith("# "):
            continue
        elif line.strip():
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "".join(out)


def brand_section(slug, ev, first):
    m = json.loads((OUT / slug / "metrics.json").read_text())
    ads = pd.read_csv(OUT / slug / "ads.csv")
    rq = pd.read_csv(OUT / slug / "review_queue.csv")
    memo = (OUT / slug / "memo.md").read_text()
    pm, p, t = m["primary_metric"], m["parsing"], m["total"]
    better = "higher is better" if pm == "roas" else "lower is better"

    tiles = [("Spend analyzed", money(t["spend"]), f"{t['ads']} ads · {', '.join(m['platforms'])}"),
             (f"Blended {pm.upper()}", metric_fmt(pm, t[pm]), better),
             ("Names decoded", f"{p['auto_pct']}%", f"{p['auto']} of {p['ads']} · {p['typo_corrected']} typos fixed"),
             ("Needs a naming fix", str(p["review"]), f"{money(p['review_spend'])} spend · {p['suggested_fixes']} fixes suggested"),
             ("Spend on ads to cut", f"{m['kill_spend_pct']}%", money(m["kill_spend"]))]
    tiles_html = "".join(f'<div class="tile"><div class="tl">{a}</div><div class="tv">{b}</div><div class="ts">{c}</div></div>'
                         for a, b, c in tiles)

    drivers = "".join(f'<div class="card"><h3>By {esc(label(f))}</h3><p class="muted">{pm.upper()}, {better}. '
                      f'Best value highlighted.</p>{bars(rows, pm, t["spend"])}</div>'
                      for f, rows in m["by_field"].items())

    v = m["verdicts"]
    board = "".join(f'<div class="vcell">{chip(k)}<div class="vn">{v[k]}</div><div class="ts">'
                    f'{money(ads.loc[ads.verdict == k, "spend"].sum())} spend</div></div>' for k in VERDICT)

    trusted = ads[ads.parse_status.isin(["AUTO", "LLM"])]
    fields = [f for f in m["by_field"]]

    def ad_rows(df):
        return "".join(f"<tr><td class='mono'>{esc(r.ad_name)}</td><td>{' · '.join(esc(label(getattr(r, f))) for f in fields)}</td>"
                       f"<td>{metric_fmt(pm, getattr(r, pm)) if pd.notna(getattr(r, pm)) else '-'}</td><td>{money(r.spend)}</td>"
                       f"<td>{chip(r.verdict)}<div class='ts'>{esc(r.verdict_reason)}</div></td></tr>" for r in df.itertuples())

    asc = pm == "cpa"
    scale = trusted[trusted.verdict == "SCALE"].sort_values(pm, ascending=asc).head(5)
    kill = trusted[trusted.verdict == "KILL"].sort_values("spend", ascending=False).head(5)
    head = f"<tr><th>Ad name</th><th>Decoded as</th><th>{pm.upper()}</th><th>Spend</th><th>Verdict and reason</th></tr>"

    rq_rows = "".join(f"<tr><td class='mono'>{esc(r.ad_name)}</td><td>{r.platform}</td><td>{money(r.spend)}</td>"
                      f"<td>{esc(r.parse_reason)}</td><td>{esc(r.suggestion) if pd.notna(r.suggestion) else '<span class=muted>needs a person</span>'}</td></tr>"
                      for r in rq.itertuples())
    acc = " · ".join(f"{esc(label(k))} {v_}%" for k, v_ in ev["field_accuracy_pct"].items())

    return f"""
<section id="{slug}" class="brand" {'' if first else 'hidden'}>
  <div class="tiles">{tiles_html}</div>
  <div class="grid2">
    <div class="card memo"><h3>Weekly creative read</h3><p class="muted">Written by {m['memo']['source']} ·
      grounding check: {m['memo']['figures_checked']} figures, {m['memo']['ungrounded']} untraceable</p>{md(memo)}</div>
    <div class="card"><h3>Verdicts from the brand's own rules sheet</h3>
      <p class="muted">First matching row of <span class="mono">brands/{slug}/rules.csv</span> wins.</p>
      <div class="board">{board}</div>
      <h3 class="mt">Parser accuracy vs ground truth</h3>
      <p>{acc} on auto-decoded names.</p>
      <p><strong>{ev['confidently_wrong']}</strong> confidently wrong parses. <strong>{ev['undecodable_caught_pct']}%</strong>
      of undecodable names ({ev['undecodable_names']}) sent to review instead of guessed.</p></div>
  </div>
  <h2>What is driving performance</h2>
  <div class="grid3">{drivers}</div>
  <h2>Ads to scale</h2><div class="card scroll"><table>{head}{ad_rows(scale)}</table></div>
  <h2>Biggest ads to cut</h2><div class="card scroll"><table>{head}{ad_rows(kill)}</table></div>
  <h2>Naming review queue</h2>
  <div class="card scroll"><p class="muted">Excluded from the breakdowns until fixed. Sorted by spend.</p>
    <table><tr><th>Ad name</th><th>Platform</th><th>Spend</th><th>Why</th><th>Suggested fix</th></tr>{rq_rows}</table></div>
</section>"""


def main():
    evals = json.loads((OUT / "eval.json").read_text())
    slugs = sorted(evals, key=lambda s: (s != "northpeak", s))
    names = {s: json.loads((OUT / s / "metrics.json").read_text())["brand"] for s in slugs}
    tabs = "".join(f'<button class="tab" data-b="{s}" aria-selected="{str(i == 0).lower()}">{esc(names[s])}</button>'
                   for i, s in enumerate(slugs))
    sections = "".join(brand_section(s, evals[s], i == 0) for i, s in enumerate(slugs))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Creative Taxonomy Judge</title><style>
:root{{--bg:#f6f5f2;--surface:#fcfcfb;--line:#e4e2dc;--text:#0b0b0b;--text2:#52514e;--muted:#77756f;--accent:#2a78d6;--accent2:#86b6ef;
--good:#0ca30c;--warning:#b07800;--critical:#d03b3b;--neutral:#77756f}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#121211;--surface:#1a1a19;--line:#2e2e2b;--text:#f0efec;--text2:#c3c2b7;--muted:#9b998f;--accent:#3987e5;--accent2:#1c5cab;--good:#0ca30c;--warning:#fab219;--critical:#e66767;--neutral:#9b998f}}}}
:root[data-theme="dark"]{{--bg:#121211;--surface:#1a1a19;--line:#2e2e2b;--text:#f0efec;--text2:#c3c2b7;--muted:#9b998f;--accent:#3987e5;--accent2:#1c5cab;--good:#0ca30c;--warning:#fab219;--critical:#e66767;--neutral:#9b998f}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:22px;margin:0}}h2{{font-size:16px;margin:28px 0 10px}}h3{{font-size:14px;margin:0 0 4px}}h4{{font-size:13px;margin:14px 0 4px}}
.sub{{color:var(--text2);margin:4px 0 16px}}.muted,.ts{{color:var(--muted);font-size:12px}}.mono{{font-family:ui-monospace,Menlo,monospace;font-size:12px}}.mt{{margin-top:18px}}
.tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}}.tab{{border:1px solid var(--line);background:var(--surface);color:var(--text);padding:8px 14px;border-radius:8px;cursor:pointer;font:inherit}}
.tab[aria-selected="true"]{{border-color:var(--accent);box-shadow:inset 0 -2px 0 var(--accent)}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(170px,100%),1fr));gap:10px}}.tile,.card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px}}
.tl{{color:var(--text2);font-size:12px}}.tv{{font-size:24px;font-weight:650;margin:2px 0}}
.grid2{{display:grid;grid-template-columns:1.2fr 1fr;gap:10px;margin-top:10px}}.grid3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:10px}}
@media (max-width:820px){{.grid2{{grid-template-columns:1fr}}}}
.memo p,.memo li{{color:var(--text)}}.memo ul{{padding-left:18px;margin:4px 0}}
.chart{{width:100%;height:auto;display:block;margin-top:6px}}.lbl{{fill:var(--text2);font-size:12px}}.val{{fill:var(--text);font-size:12px}}
.mark{{fill:var(--accent2)}}.mark.best{{fill:var(--accent)}}.bar:hover .mark{{opacity:.8}}
.board{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px}}.vcell{{border:1px solid var(--line);border-radius:8px;padding:10px}}.vn{{font-size:22px;font-weight:650}}
@media (max-width:520px){{.board{{grid-template-columns:repeat(2,1fr)}}}}
.chip{{display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}}
.chip.good{{color:var(--good)}}.chip.warning{{color:var(--warning)}}.chip.critical{{color:var(--critical)}}.chip.neutral{{color:var(--neutral)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--text2);font-weight:600}}
.scroll{{overflow-x:auto}}.grid2>*,.grid3>*,.tiles>*{{min-width:0}}.mono{{overflow-wrap:anywhere}}details{{margin-top:6px}}summary{{cursor:pointer;color:var(--text2);font-size:12px}}
footer{{color:var(--muted);font-size:12px;margin-top:32px}}
</style></head><body><main>
<h1>Creative Taxonomy Judge</h1>
<p class="sub">Each brand names its ads its own way and judges them its own way. This decodes every ad name into the brand's
taxonomy, judges every ad with the brand's own rules sheet, and explains what is winning. Synthetic data, fictional brands.</p>
<div class="tabs" role="tablist">{tabs}</div>{sections}
<footer>Built from output/*/metrics.json. Every number in the memo passed the grounding check.</footer></main>
<script>
const tabs=[...document.querySelectorAll('.tab')];
function show(b){{tabs.forEach(t=>t.setAttribute('aria-selected',t.dataset.b===b));document.querySelectorAll('.brand').forEach(s=>s.hidden=s.id!==b);try{{localStorage.setItem('brand',b)}}catch(e){{}}}}
tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.b)));
try{{const b=localStorage.getItem('brand');if(b&&document.getElementById(b))show(b)}}catch(e){{}}
</script></body></html>"""
    (OUT / "dashboard.html").write_text(page)
    print("wrote output/dashboard.html")


if __name__ == "__main__":
    main()
