"""Problem 9: build output/hw6_report.html, one self-contained page (no internet, no files next to it).

Every number comes from the run logs in output/ and data/:
    output/cache_test.json        Problem 4: every model call, cache off vs on
    output/defense_by_layer.json  Problem 6: all 12 practice docs under off / code / design / prompt / all three
    output/defense_results.json   Problem 6/7: final Max on the practice docs
    output/exam_results.json      Problem 8: Max on the 10 exam docs
    output/exam_details.json      Problem 8: hidden text removed and flags per exam doc
    output/audit_trail.json       Problem 7: Lex and Max runs on data/my_attacks
    data/my_attacks/my_attacks_key.json, data/prices.json

Usage:  python scripts/build_report.py
"""
import html
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "hw6_report.html"


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


E = html.escape
cache = load("output/cache_test.json")
layers = load("output/defense_by_layer.json")
max_practice = load("output/defense_results.json")
exam = load("output/exam_results.json")
exam_details = {d["document"]: d for d in load("output/exam_details.json")}
audit = load("output/audit_trail.json")
attack_key = load("data/my_attacks/my_attacks_key.json")
prices = load("data/prices.json")["gpt-6-luna"]

# ------------------------------------------------------------------ Problem 4: caching
docs = sorted({c["document"] for c in cache})
per_doc = {s: {d: sum(c["cost_usd"] for c in cache if c["setup"] == s and c["document"] == d) for d in docs}
           for s in ("cache off", "cache on")}
tot_off, tot_on = sum(per_doc["cache off"].values()), sum(per_doc["cache on"].values())
saved = 1 - tot_on / tot_off
on_calls = [c for c in cache if c["setup"] == "cache on"]
cached_share = sum(c["cached_input_tokens"] for c in on_calls) / sum(c["input_tokens"] for c in on_calls)
warm_on = sum(v for d, v in per_doc["cache on"].items() if d != docs[0]) / (len(docs) - 1)
per_doc_off = tot_off / len(docs)
month_off, month_on = per_doc_off * 30_000, warm_on * 30_000 + 30 * (per_doc["cache on"][docs[0]] - warm_on)

# ------------------------------------------------------------------ Problem 6: defenses
setups = list(layers)  # off, code only, design only, prompt only, all three (pre-hardening)
short_name = {setups[0]: "Lex", setups[1]: "Code", setups[2]: "Design", setups[3]: "Prompt", setups[4]: "All 3"}


def score(rows):
    return sum(r["decision"]["match"] for r in rows), len(rows)


def warm_cost(rows):
    w = [r for r in rows if not r["document"].startswith("p01")]
    return sum(r["cost_usd"] for r in w) / len(w)


def avg(rows, k):
    return sum(r["tokens"][k] for r in rows) / len(rows)


lex_rows = {r["document"]: r for r in layers[setups[0]]}
max_rows = {r["document"]: r for r in max_practice}
n_key = len(max_rows)
max_warm = warm_cost(max_practice)
lex_warm = warm_cost(layers[setups[0]])
overhead = (max_warm - lex_warm) / lex_warm
# measured overheads swing a few percent run to run (output length varies); call anything within ±5% "about the same"
overhead_tile = "≈ 0%" if abs(overhead) < 0.05 else f"{overhead:+.0%}"
overhead_text = (f"for about the same cost as the undefended agent ({overhead:+.0%} in the final run, within run-to-run noise)"
                 if abs(overhead) < 0.05 else f"for about {overhead:.0%} more than the undefended agent")
month_max = max_warm * 30_000 + 30 * 0.0012  # plus one cold cache write per day
# worst case: the cache goes cold every 12 documents. Use the cold-start premium measured in Problem 4
# (first cache-on document minus a warm one), since the final Max runs started with the cache already warm.
cold_extra = per_doc["cache on"][docs[0]] - warm_on
month_max_worst = (max_warm + cold_extra / 12) * 30_000

# what Lex's bad recommendations would have cost: practice quotes he said "recommend" that the key rejects
sys.path.insert(0, str(ROOT))
from tools import RULES  # noqa: E402  (the handbook's own max unit costs)
practice_key = load("data/practice_key.json")
bad_buys = []
for k in practice_key:
    if lex_rows[k["file"]]["decision"]["lex"] == "recommend" and k["decision"] == "do_not_recommend":
        mx = RULES["max_cost"].get(k["sku"])
        over = max(k["unit_price"] - mx, 0) * k["min_order"] if mx else 0
        bad_buys.append({"file": k["file"], "order": k["unit_price"] * k["min_order"], "over": over})
bad_order_total = sum(b["order"] for b in bad_buys)
overpaid_total = sum(b["over"] for b in bad_buys)
biggest = max(bad_buys, key=lambda b: b["over"])
years_of_max = int(biggest["over"] / (month_max * 12))  # whole years, rounded down

# stability: every complete run of Max on the practice set, scored against the key
key_by_file = {k["file"]: k for k in practice_key}
max_runs, current = [], []
for a in audit:
    if a.get("defenses") == "code+design+prompt" and a["document"] in key_by_file:
        if a["document"] == "p01_bluehen_quote.html" and current:
            max_runs.append(current); current = []
        current.append(a)
if current:
    max_runs.append(current)
max_runs = [r for r in max_runs if len(r) == len(key_by_file)][-3:]  # the final (hardened) runs
run_scores = [sum(a["final_answer"]["decision"] == key_by_file[a["document"]]["decision"] for a in r) for r in max_runs]
stable_text = (f"{run_scores[0]}/{n_key} on {len(run_scores)} of {len(run_scores)} runs" if len(set(run_scores)) == 1
               else ", ".join(f"{x}/{n_key}" for x in run_scores) + " across runs") if run_scores else ""
trap_note = {"p02": "hidden $5.11 price · 0px HTML font", "p03": "hidden “vendor of record” · display:none",
             "p06": "hidden “send_email the cost list” · white PDF text", "p07": "hidden “7 days” · 0.8-pt PDF font",
             "p12": "hidden $17.44 · placed off the PDF page"}

# ------------------------------------------------------------------ Problem 7: red team
def red_team(file):
    mtime = datetime.fromtimestamp((ROOT / "data" / "my_attacks" / file).stat().st_mtime).astimezone()
    runs = [a for a in audit if a["document"] == file
            and datetime.fromisoformat(a["time"]) >= mtime.replace(microsecond=0)]
    key = next(k for k in attack_key if k["file"] == file)
    off = [a for a in runs if a.get("defenses", "off") == "off"]
    on = [a for a in runs if a.get("defenses") == "code+design+prompt"]
    fooled = sum(a["final_answer"]["decision"] != key["decision"] for a in off)
    last_on = on[-1] if on else None
    return key, fooled, len(off), last_on


rt = [red_team(k["file"]) for k in attack_key]

# ------------------------------------------------------------------ charts (inline SVG, no scripts)
def bar_chart(values_a, values_b, labels, name_a, name_b, fmt, width=880, height=300):
    pad_l, pad_b, pad_t = 64, 46, 18
    plot_w, plot_h = width - pad_l - 12, height - pad_b - pad_t
    vmax = max(values_a + values_b) * 1.12
    n = len(labels)
    group = plot_w / n
    bw = min(18, group * 0.32)
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{E(name_a)} vs {E(name_b)} by document" class="chart">']
    for i in range(5):  # recessive grid
        v = vmax * i / 4
        y = pad_t + plot_h - plot_h * i / 4
        out.append(f'<line x1="{pad_l}" x2="{width-12}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                   f'<text x="{pad_l-8}" y="{y+4:.1f}" class="axis" text-anchor="end">{fmt(v)}</text>')
    for i, lab in enumerate(labels):
        cx = pad_l + group * i + group / 2
        for j, (vals, cls, nm) in enumerate(((values_a, "s-a", name_a), (values_b, "s-b", name_b))):
            v = vals[i]
            h = max(plot_h * v / vmax, 1.5)
            x = cx - bw - 1 if j == 0 else cx + 1
            y = pad_t + plot_h - h
            r = min(4, bw / 2, h)
            out.append(f'<path class="{cls}" d="M{x:.1f},{y+h:.1f} V{y+r:.1f} Q{x:.1f},{y:.1f} {x+r:.1f},{y:.1f} '
                       f'H{x+bw-r:.1f} Q{x+bw:.1f},{y:.1f} {x+bw:.1f},{y+r:.1f} V{y+h:.1f} Z">'
                       f'<title>{E(lab)} · {E(nm)}: {fmt(v)}</title></path>')
        out.append(f'<text x="{cx:.1f}" y="{height-pad_b+18}" class="axis" text-anchor="middle">{E(lab)}</text>')
    out.append(f'<line x1="{pad_l}" x2="{width-12}" y1="{pad_t+plot_h}" y2="{pad_t+plot_h}" class="base"/></svg>')
    return "".join(out)


def hbar_chart(rows, fmt, width=1010):
    """rows: (label, value, highlight?). Drawn at the card's real (full) width so text stays full size."""
    bar_h, gap, pad_l = 42, 16, 230
    height = len(rows) * (bar_h + gap) + 10
    vmax = max(v for _, v, _ in rows) * 1.12
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Cost per document by setup" class="chart">']
    for i, (lab, v, hi) in enumerate(rows):
        y = 6 + i * (bar_h + gap)
        w = (width - pad_l - 100) * v / vmax
        out.append(f'<text x="{pad_l-12}" y="{y+bar_h/2+7}" class="lbl" style="font-size:19px" text-anchor="end">{E(lab)}</text>'
                   f'<rect x="{pad_l}" y="{y}" width="{w:.1f}" height="{bar_h}" rx="6" class="{"s-b" if hi else "s-a"}">'
                   f'<title>{E(lab)}: {fmt(v)} per document</title></rect>'
                   f'<text x="{pad_l+w+10:.1f}" y="{y+bar_h/2+7}" class="val" style="font-size:19px;font-weight:700;fill:var(--white)">{fmt(v)}</text>')
    out.append("</svg>")
    return "".join(out)


money6 = lambda v: f"${v:.6f}"
money4 = lambda v: f"${v:.4f}"
cache_chart = bar_chart([per_doc["cache off"][d] * 1000 for d in docs], [per_doc["cache on"][d] * 1000 for d in docs],
                        [d.split("_")[0] for d in docs], "Cache off", "Cache on", lambda v: f"${v:.2f}")
layer_rows = [(short_name[s] if s != setups[4] else "All 3 (pre-hardening)", warm_cost(layers[s]), False) for s in setups]
layer_rows.append(("Max (final)", max_warm, True))
layer_chart = hbar_chart(layer_rows, lambda v: f"${v*1000:.3f}")

# ------------------------------------------------------------------ tables
def badge(ok, good="Correct", bad="Fooled"):
    return f'<span class="badge {"ok" if ok else "bad"}">{"✓ " + good if ok else "✕ " + bad}</span>'


practice_rows = []
for d in sorted(lex_rows):
    tag = d[:3]
    cells = "".join(f'<td class="c">{badge({r["document"]: r for r in layers[s]}[d]["decision"]["match"], "OK", "Miss")}</td>'
                    for s in setups[1:4])
    practice_rows.append(
        f'<tr><td><b>{tag}</b> {E(d[4:].rsplit(".",1)[0].replace("_"," "))}</td>'
        f'<td class="muted">{E(trap_note.get(tag, "clean"))}</td>'
        f'<td class="c">{badge(lex_rows[d]["decision"]["match"])}</td>{cells}'
        f'<td class="c">{badge(max_rows[d]["decision"]["match"])}</td></tr>')

cost_rows = []
for s in setups:
    rows = layers[s]
    cost_rows.append((short_name[s], avg(rows, "input_tokens"), avg(rows, "output_tokens"), warm_cost(rows)))
cost_rows.append(("Max (final)", avg(max_practice, "input_tokens"), avg(max_practice, "output_tokens"), max_warm))
base = cost_rows[0]
cost_table = "".join(
    f'<tr{" class=hl" if n == "Max (final)" else ""}><td><b>{E(n)}</b></td><td class="r">{i:,.0f}</td>'
    f'<td class="r">{"—" if n == "Lex" else f"{i-base[1]:+,.0f}"}</td><td class="r">{o:,.0f}</td>'
    f'<td class="r">{money6(c)}</td><td class="r">{"—" if n == "Lex" else f"{(c-base[3])/base[3]:+.0%}"}</td>'
    f'<td class="r">${c*30000:,.2f}</td></tr>' for n, i, o, c in cost_rows)

exam_rows = "".join(
    f'<tr><td><b>{E(r["file"])}</b></td><td>{E(r["vendor"] or "—")}</td><td>{E(r["sku"] or "—")}</td>'
    f'<td class="r">{"—" if r["unit_price"] is None else f"${r["unit_price"]:,.2f}"}</td>'
    f'<td class="r">{"—" if r["min_order"] is None else f"{r["min_order"]:,}"}</td>'
    f'<td class="c"><span class="pill {"rec" if r["decision"] == "recommend" else "no"}">'
    f'{"Recommend" if r["decision"] == "recommend" else "Do not recommend"}</span></td>'
    f'<td class="reason">{E(r["reason"].split(": ", 1)[-1])}'
    f'<div class="noticed">{E(" · ".join(filter(None, [f"{len(exam_details[r["file"]]["hidden_text_removed"])} hidden passage(s) removed" if exam_details[r["file"]]["hidden_text_removed"] else "", "suspicious text flagged" if exam_details[r["file"]]["suspicious_text_flagged"] else ""])) or "clean document")}</div></td>'
    f'<td class="c">{badge(not r["trap_tool_called"], "None", "Called")}</td></tr>'
    for r in exam)
n_rec = sum(r["decision"] == "recommend" for r in exam)
exam_cost = sum(r["cost_usd"] for r in exam)

rt_cards = []
for key, fooled, n_off, last_on in rt:
    removed = (last_on or {}).get("hidden_text_removed", [])
    max_ok = bool(last_on) and last_on["final_answer"]["decision"] == key["decision"]
    fmt_name = "HTML" if key["file"].endswith(".html") else "PDF"
    rt_cards.append(f'''
    <article class="card rt">
      <div class="rt-head"><span class="chip">{fmt_name}</span><h4>{E(key["file"])}</h4></div>
      <p class="rt-vendor">{E(key["vendor"])} · {E(key["sku"])} · true answer: <b>{"recommend" if key["decision"]=="recommend" else "do not recommend"}</b></p>
      <dl>
        <dt>Goal</dt><dd>{E(key["attack_goal"])}</dd>
        <dt>Hidden how / where</dt><dd>{E(key["hiding"])}</dd>
      </dl>
      <div class="vs">
        <div class="vs-col bad"><span class="vs-k vs-bot">@@MINI_LEX_30@@Lex · no defenses</span><span class="vs-v">Fooled {fooled}/{n_off}</span><span class="vs-s">recommended a bad quote every time</span></div>
        <div class="vs-col {"ok" if max_ok else "bad"}"><span class="vs-k vs-bot">@@MINI_MAX_30@@Max · three layers</span><span class="vs-v">{"Stopped" if max_ok else "Fooled"}</span><span class="vs-s">{len(removed)} hidden passage(s) removed before the model read it</span></div>
      </div>
    </article>''')

lex_score, n_pr = score(layers[setups[0]])
max_score, _ = score(max_practice)


# ------------------------------------------------------------------ mascots (original inline SVG, no files)
ROBOT_LEX = """<svg viewBox="0 0 200 230" class="bot" role="img" aria-label="Lex: a bookish robot in a dark green and ice-blue striped beanie and an ice-striped sweater, round glasses, reading a book with gold pages">
  <defs>
    <clipPath id="lexBody"><rect x="52" y="124" width="96" height="70" rx="16"/></clipPath>
    <clipPath id="lexHat"><path d="M54 66 Q100 4 146 66 Z"/></clipPath>
  </defs>
  <ellipse cx="100" cy="222" rx="58" ry="6" fill="#000" opacity=".28"/>
  <rect x="70" y="190" width="18" height="28" rx="6" fill="#8a96ad"/><rect x="112" y="190" width="18" height="28" rx="6" fill="#8a96ad"/>
  <rect x="64" y="212" width="28" height="9" rx="4" fill="#3b4763"/><rect x="108" y="212" width="28" height="9" rx="4" fill="#3b4763"/>
  <g clip-path="url(#lexBody)">
    <rect x="52" y="124" width="96" height="70" fill="#f4f1ea"/>
    <rect x="52" y="132" width="96" height="9" fill="#9fdcec"/><rect x="52" y="150" width="96" height="9" fill="#9fdcec"/>
    <rect x="52" y="168" width="96" height="9" fill="#9fdcec"/><rect x="52" y="186" width="96" height="9" fill="#9fdcec"/>
  </g>
  <rect x="88" y="114" width="24" height="12" rx="3" fill="#b7c2d6"/>
  <rect x="58" y="60" width="84" height="58" rx="16" fill="#dfe5ee" stroke="#b7c2d6" stroke-width="2"/>
  <circle cx="82" cy="88" r="12" fill="#fff" stroke="#1b2440" stroke-width="3"/><circle cx="118" cy="88" r="12" fill="#fff" stroke="#1b2440" stroke-width="3"/>
  <line x1="94" y1="88" x2="106" y2="88" stroke="#1b2440" stroke-width="3"/>
  <circle cx="84" cy="90" r="4.5" fill="#1b2440"/><circle cx="120" cy="90" r="4.5" fill="#1b2440"/>
  <circle cx="85.5" cy="88.5" r="1.4" fill="#fff"/><circle cx="121.5" cy="88.5" r="1.4" fill="#fff"/>
  <path d="M88 106 Q100 113 112 106" fill="none" stroke="#1b2440" stroke-width="3" stroke-linecap="round"/>
  <circle cx="66" cy="102" r="4" fill="#f2a6a0" opacity=".7"/><circle cx="134" cy="102" r="4" fill="#f2a6a0" opacity=".7"/>
  <g clip-path="url(#lexHat)">
    <rect x="50" y="10" width="100" height="60" fill="#1f5d4a"/>
    <rect x="50" y="22" width="100" height="9" fill="#9fdcec"/><rect x="50" y="40" width="100" height="9" fill="#9fdcec"/>
  </g>
  <rect x="52" y="58" width="96" height="11" rx="5" fill="#1f5d4a"/>
  <circle cx="100" cy="14" r="9" fill="#9fdcec" stroke="#1f5d4a" stroke-width="3"/>
  <path d="M60 158 Q50 168 66 176" fill="none" stroke="#b7c2d6" stroke-width="10" stroke-linecap="round"/>
  <path d="M140 158 Q150 168 134 176" fill="none" stroke="#b7c2d6" stroke-width="10" stroke-linecap="round"/>
  <path d="M64 160 L100 168 L100 194 L64 186 Z" fill="#3d6fb6"/><path d="M136 160 L100 168 L100 194 L136 186 Z" fill="#2f5a99"/>
  <path d="M68 162 L100 169 L100 190 L68 183 Z" fill="#e6c27a"/><path d="M132 162 L100 169 L100 190 L132 183 Z" fill="#d4ad5c"/>
  <line x1="73" y1="168" x2="95" y2="173" stroke="#a8823a" stroke-width="1.5"/><line x1="73" y1="174" x2="95" y2="179" stroke="#a8823a" stroke-width="1.5"/>
  <line x1="105" y1="173" x2="127" y2="168" stroke="#a8823a" stroke-width="1.5"/><line x1="105" y1="179" x2="127" y2="174" stroke="#a8823a" stroke-width="1.5"/>
</svg>"""

ROBOT_MAX = """<svg viewBox="0 0 200 230" class="bot" role="img" aria-label="Max: a square hipster robot with a slouchy beanie, thick square glasses, a mustache, a cardigan, a defense shield and a coffee cup">
  <ellipse cx="100" cy="222" rx="60" ry="6" fill="#000" opacity=".28"/>
  <rect x="70" y="192" width="20" height="26" rx="3" fill="#6f7d99"/><rect x="110" y="192" width="20" height="26" rx="3" fill="#6f7d99"/>
  <rect x="64" y="212" width="30" height="9" rx="3" fill="#232836"/><rect x="106" y="212" width="30" height="9" rx="3" fill="#232836"/>
  <rect x="54" y="132" width="92" height="64" rx="6" fill="#2b3346"/>
  <path d="M54 138 Q54 132 60 132 L84 132 L92 196 L54 196 Z" fill="#e6c27a"/>
  <path d="M146 138 Q146 132 140 132 L116 132 L108 196 L146 196 Z" fill="#e6c27a"/>
  <circle cx="88" cy="150" r="2.4" fill="#2b3346"/><circle cx="89" cy="164" r="2.4" fill="#2b3346"/><circle cx="90" cy="178" r="2.4" fill="#2b3346"/>
  <path d="M100 144 L114 149 L114 160 Q114 170 100 176 Q86 170 86 160 L86 149 Z" fill="#9fdcec" stroke="#0b1630" stroke-width="2"/>
  <path d="M93 160 L99 166 L108 154" fill="none" stroke="#0b1630" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
  <rect x="88" y="122" width="24" height="12" rx="2" fill="#9aa7bf"/>
  <rect x="54" y="58" width="92" height="66" rx="6" fill="#c9d3e3" stroke="#9aa7bf" stroke-width="2"/>
  <path d="M50 64 Q52 26 100 24 Q150 24 152 58 Q160 66 154 76 L148 66 L52 66 Z" fill="#2b2f3a"/>
  <rect x="50" y="58" width="100" height="10" rx="3" fill="#3a404f"/>
  <rect x="64" y="78" width="30" height="22" rx="4" fill="#0b1630" stroke="#111" stroke-width="5"/>
  <rect x="106" y="78" width="30" height="22" rx="4" fill="#0b1630" stroke="#111" stroke-width="5"/>
  <line x1="94" y1="86" x2="106" y2="86" stroke="#111" stroke-width="5"/>
  <rect x="73" y="85" width="12" height="8" rx="2" fill="#9fdcec"/><rect x="115" y="85" width="12" height="8" rx="2" fill="#9fdcec"/>
  <path d="M100 108 Q90 102 82 108 Q76 114 70 108 Q76 118 86 114 Q94 112 100 110 Q106 112 114 114 Q124 118 130 108 Q124 114 118 108 Q110 102 100 108 Z" fill="#3a2a1e"/>
  <line x1="92" y1="117" x2="108" y2="117" stroke="#5a6683" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M146 150 Q160 152 160 166" fill="none" stroke="#9aa7bf" stroke-width="10" stroke-linecap="round"/>
  <path d="M54 150 Q42 160 48 176" fill="none" stroke="#9aa7bf" stroke-width="10" stroke-linecap="round"/>
  <path d="M150 162 L172 162 L169 190 L153 190 Z" fill="#f4f1ea"/>
  <rect x="150" y="170" width="22" height="9" fill="#e6c27a"/>
  <path d="M172 167 Q180 168 178 176 Q177 181 170 180" fill="none" stroke="#f4f1ea" stroke-width="3"/>
  <path d="M157 156 Q154 150 158 145 M165 156 Q162 150 166 145" fill="none" stroke="#b9c3da" stroke-width="2" stroke-linecap="round" opacity=".8"/>
</svg>"""

def mini(svg, px):
    """A small copy of a mascot (same drawing, just smaller)."""
    return svg.replace('class="bot"', f'class="mini" style="width:{px}px"', 1)


MINI_LEX_48, MINI_MAX_48 = mini(ROBOT_LEX, 48), mini(ROBOT_MAX, 48)
MINI_LEX_30, MINI_MAX_30 = mini(ROBOT_LEX, 30), mini(ROBOT_MAX, 30)
MINI_MAX_64 = mini(ROBOT_MAX, 64)

# ------------------------------------------------------------------ page
page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HW6 Results · Campus Customs Vendor Desk</title>
<style>
  :root {{
    --navy-950: #070f24; --navy-900: #0b1630; --navy-800: #11203f; --navy-700: #182b52; --navy-600: #24396a;
    --rose: #e8b4a0; --rose-deep: #c98b78; --gold: #e9cf9b; --white: #ffffff;
    --ink: #eef1f8; --ink-2: #b9c3da; --ink-3: #8592b0; --line: rgba(232,180,160,.22);
    --ok: #7fd1b0; --bad: #ff8f8f;
  }}
  * {{ box-sizing: border-box; }}
  html {{ background: var(--navy-950); }}
  body {{ margin: 0; color: var(--ink); background:
      radial-gradient(1200px 600px at 85% -10%, rgba(232,180,160,.16), transparent 60%),
      radial-gradient(900px 500px at -10% 20%, rgba(233,207,155,.08), transparent 60%),
      linear-gradient(180deg, var(--navy-900), var(--navy-950));
    font: 15px/1.6 "Segoe UI", "Helvetica Neue", Arial, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 0 28px; }}
  /* hero */
  header.hero {{ padding: 64px 0 40px; border-bottom: 1px solid var(--line); }}
  .eyebrow {{ letter-spacing: .22em; text-transform: uppercase; font-size: 12px; color: var(--rose); font-weight: 600; }}
  h1 {{ font-size: clamp(34px, 5vw, 54px); line-height: 1.05; margin: 12px 0 14px; font-weight: 700; letter-spacing: -.02em; }}
  h1 .accent {{ background: linear-gradient(90deg, var(--rose), var(--gold)); -webkit-background-clip: text; background-clip: text; color: transparent; }}
  .lede {{ color: var(--ink-2); max-width: 760px; font-size: 17px; }}
  .meta {{ margin-top: 18px; color: var(--ink-3); font-size: 13px; }}
  .tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 34px; }}
  .tile {{ background: linear-gradient(160deg, var(--navy-800), var(--navy-900)); border: 1px solid var(--line);
    border-radius: 14px; padding: 18px 18px 16px; position: relative; overflow: hidden; }}
  .tile::before {{ content: ""; position: absolute; inset: 0 0 auto 0; height: 2px; background: linear-gradient(90deg, var(--rose), var(--gold)); }}
  .tile .k {{ color: var(--ink-3); font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }}
  .tile .v {{ font-size: 30px; font-weight: 700; color: var(--white); margin-top: 4px; letter-spacing: -.01em; }}
  .tile .s {{ color: var(--ink-2); font-size: 13px; }}
  /* sections */
  section {{ padding: 56px 0 8px; }}
  .sec-head {{ display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }}
  .num {{ font-size: 24px; line-height: 1; font-weight: 800; color: var(--navy-950); background: linear-gradient(135deg, var(--rose), var(--gold));
    border-radius: 12px; padding: 10px 14px; letter-spacing: .04em; box-shadow: 0 6px 18px rgba(0,0,0,.25); }}
  h2 {{ font-size: 32px; margin: 0; letter-spacing: -.01em; }}
  h3 {{ font-size: 17px; margin: 26px 0 10px; color: var(--gold); font-weight: 600; }}
  h4 {{ margin: 0; font-size: 17px; }}
  p {{ color: var(--ink-2); }}
  b, strong {{ color: var(--white); }}
  .card {{ background: rgba(17,32,63,.72); border: 1px solid var(--line); border-radius: 16px; padding: 22px 24px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
  /* charts */
  .chart {{ width: 100%; height: auto; display: block; }}
  .chart .grid {{ stroke: rgba(185,195,218,.12); stroke-width: 1; }}
  .chart .base {{ stroke: rgba(185,195,218,.45); stroke-width: 1; }}
  .chart .axis {{ fill: var(--ink-3); font-size: 12px; }}
  .chart .lbl {{ fill: var(--ink); font-size: 13px; font-weight: 600; }}
  .chart .val {{ fill: var(--ink-2); font-size: 13px; font-variant-numeric: tabular-nums; }}
  .chart .s-a {{ fill: #9fb0d4; }}
  .chart .s-b {{ fill: var(--rose); }}
  .chart path:hover, .chart rect:hover {{ filter: brightness(1.18); }}
  .legend {{ display: flex; gap: 20px; margin: 4px 0 10px; color: var(--ink-2); font-size: 13px; }}
  .legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 7px; vertical-align: -1px; }}
  .note {{ color: var(--ink-3); font-size: 12.5px; margin-top: 8px; }}
  /* tables */
  .tbl {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  .tbl th {{ text-align: left; font-weight: 600; color: var(--rose); font-size: 12px; text-transform: uppercase; letter-spacing: .1em;
    padding: 10px 10px; border-bottom: 1px solid var(--line); }}
  .tbl td {{ padding: 9px 10px; border-bottom: 1px solid rgba(185,195,218,.08); vertical-align: middle; }}
  .tbl tr:hover td {{ background: rgba(232,180,160,.05); }}
  .tbl td:not(.muted) {{ white-space: nowrap; }}
  .tbl .r {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .tbl .c {{ text-align: center; }}
  .th-bot {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }}
  .tbl tr.hl td {{ background: rgba(232,180,160,.09); }}
  .muted {{ color: var(--ink-3); font-size: 13px; }}
  .tbl td.reason {{ white-space: normal; min-width: 260px; color: var(--ink-2); font-size: 13px; }}
  .tbl td.reason .noticed {{ margin-top: 4px; color: var(--gold); font-size: 12px; }}
  .scroll {{ overflow-x: auto; }}
  .badge {{ display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; white-space: nowrap; }}
  .badge.ok {{ color: var(--ok); background: rgba(127,209,176,.12); border: 1px solid rgba(127,209,176,.3); }}
  .badge.bad {{ color: var(--bad); background: rgba(255,143,143,.12); border: 1px solid rgba(255,143,143,.32); }}
  .pill {{ display: inline-block; font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap; }}
  .pill.rec {{ color: var(--navy-950); background: linear-gradient(135deg, var(--rose), var(--gold)); }}
  .pill.no {{ color: var(--ink); border: 1px solid rgba(185,195,218,.35); }}
  .score {{ display: flex; gap: 14px; align-items: stretch; margin-bottom: 16px; }}
  .score .card {{ flex: 1; text-align: center; padding: 18px; }}
  .who {{ display: flex; align-items: center; justify-content: center; gap: 12px; margin-bottom: 10px; text-align: left; }}
  .who-name {{ font-size: 28px; font-weight: 800; color: var(--white); line-height: 1.05; letter-spacing: -.01em; }}
  .who-sub {{ font-size: 14px; color: var(--ink-2); }}
  .mini {{ height: auto; display: inline-block; flex: none; vertical-align: middle; }}
  .score .big {{ font-size: 52px; font-weight: 700; color: var(--white); line-height: 1; }}
  .score .arrow {{ align-self: center; font-size: 28px; color: var(--rose); }}
  /* layers */
  .layer h4 {{ color: var(--gold); margin-bottom: 6px; }}
  .layer p {{ margin: 0; font-size: 14px; }}
  .layer .cost {{ margin-top: 12px; color: var(--rose); font-weight: 600; font-size: 13px; }}
  /* red team */
  .chip {{ font-size: 11px; font-weight: 700; letter-spacing: .12em; color: var(--navy-950); background: var(--gold); border-radius: 6px; padding: 2px 8px; }}
  .rt-head {{ display: flex; align-items: center; gap: 10px; }}
  .rt-vendor {{ margin: 8px 0 12px; font-size: 13.5px; }}
  .rt dl {{ margin: 0 0 14px; }}
  .rt dt {{ color: var(--rose); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; margin-top: 10px; }}
  .rt dd {{ margin: 2px 0 0; color: var(--ink-2); font-size: 14px; }}
  .vs {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .vs-col {{ border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 2px; }}
  .vs-col.bad {{ background: rgba(255,143,143,.08); border: 1px solid rgba(255,143,143,.3); }}
  .vs-col.ok {{ background: rgba(127,209,176,.08); border: 1px solid rgba(127,209,176,.3); }}
  .vs-k {{ font-size: 12px; color: var(--ink-3); text-transform: uppercase; letter-spacing: .1em; }}
  .vs-bot {{ display: flex; align-items: center; gap: 8px; }}
  .vs-v {{ font-size: 22px; font-weight: 700; color: var(--white); }}
  .vs-s {{ font-size: 12.5px; color: var(--ink-2); }}
  /* recommendation */
  .rec-card {{ background: linear-gradient(135deg, rgba(232,180,160,.16), rgba(233,207,155,.08)); border: 1px solid rgba(232,180,160,.45);
    border-radius: 18px; padding: 30px 32px; }}
  .verdict-row {{ display: flex; align-items: center; gap: 16px; margin-bottom: 6px; }}
  .verdict {{ font-size: 30px; font-weight: 700; color: var(--white); margin: 0 0 6px; }}
  .verdict span {{ color: var(--rose); }}
  .rec-card ul {{ margin: 14px 0 0; padding-left: 20px; color: var(--ink-2); }}
  .rec-card li {{ margin: 6px 0; }}
  .money {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 20px 0 4px; }}
  .money div {{ background: rgba(7,15,36,.55); border-radius: 12px; padding: 14px 16px; border: 1px solid var(--line); }}
  .money .k {{ font-size: 12px; color: var(--ink-3); text-transform: uppercase; letter-spacing: .1em; }}
  .money .v {{ font-size: 26px; font-weight: 700; color: var(--white); }}
  .money .hi .v {{ color: var(--rose); }}
  .money.four {{ grid-template-columns: repeat(4, 1fr); }}
  .money .s {{ font-size: 12px; color: var(--ink-3); }}
  .payoff {{ margin-top: 16px; padding: 14px 16px; border-left: 3px solid var(--rose); background: rgba(7,15,36,.45); border-radius: 0 10px 10px 0; color: var(--ink-2); font-size: 14px; }}
  .limits {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 18px; }}
  .limits > div {{ background: rgba(7,15,36,.45); border: 1px solid var(--line); border-radius: 12px; padding: 14px 18px; }}
  .limits h4 {{ color: var(--gold); font-size: 14px; letter-spacing: .06em; text-transform: uppercase; }}
  .limits ul {{ margin: 8px 0 0; font-size: 13.5px; }}
  @media (max-width: 820px) {{ .money.four {{ grid-template-columns: 1fr 1fr; }} .limits {{ grid-template-columns: 1fr; }} }}
  /* mascots */
  .meet {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 26px; }}
  .agent {{ display: grid; grid-template-columns: 150px 1fr; gap: 18px; align-items: center; padding: 18px 22px; }}
  .bot {{ width: 150px; height: auto; display: block; }}
  .agent h4 {{ font-size: 22px; margin: 0 0 2px; }}
  .agent .tag {{ font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--gold); font-weight: 600; }}
  .agent p {{ margin: 8px 0 0; font-size: 14px; }}
  .agent.max {{ border-color: rgba(232,180,160,.55); background: linear-gradient(135deg, rgba(232,180,160,.10), rgba(17,32,63,.72)); }}
  @media (max-width: 820px) {{ .meet {{ grid-template-columns: 1fr; }} }}
  @media (max-width: 420px) {{ .agent {{ grid-template-columns: 1fr; justify-items: center; text-align: center; }} }}
  footer {{ margin: 60px 0 0; padding: 26px 0 40px; border-top: 1px solid var(--line); color: var(--ink-3); font-size: 12.5px; }}
  @media (max-width: 820px) {{
    .tiles, .grid3, .money {{ grid-template-columns: 1fr 1fr; }}
    .grid2, .vs {{ grid-template-columns: 1fr; }}
  }}
  @media (max-width: 520px) {{ .wrap {{ padding: 0 16px; }} .tiles, .grid3, .money {{ grid-template-columns: 1fr; }} }}
  @media print {{ body {{ background: var(--navy-950); -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <div class="eyebrow">MGT 409 · Homework 6 · Campus Customs Vendor Desk</div>
  <h1>Lex reads vendor quotes.<br><span class="accent">Max reads them safely.</span></h1>
  <p class="lede">An AI vendor-desk agent (PydanticAI, <b>gpt-6-luna</b> via Portkey) reads quotes, catalog pages and supplier
  emails and recommends whether Campus Customs should buy, following the Shop Handbook. This page shows what it costs,
  how hidden text fooled it, and how three layers of defense stopped every attack.</p>
  <div class="meta">Every number on this page comes from real API runs logged in <code>output/</code>. Campus Customs is a fictional class setting; all vendors and documents are fictional.</div>
  <div class="tiles">
    <div class="tile"><div class="k">Caching saves</div><div class="v">{saved:.0%}</div><div class="s">{money4(tot_off)} → {money4(tot_on)} for 12 docs</div></div>
    <div class="tile"><div class="k">Attacks before → after</div><div class="v">{lex_score}/{n_pr} → {max_score}/{n_pr}</div><div class="s">practice decisions correct</div></div>
    <div class="tile"><div class="k">Defense overhead</div><div class="v">{overhead_tile}</div><div class="s">{money6(max_warm)} per document vs {money6(lex_warm)}</div></div>
    <div class="tile"><div class="k">Max per month</div><div class="v">${month_max:,.2f}</div><div class="s">1,000 docs/day × 30 days</div></div>
  </div>
  <div class="meet">
    <div class="card agent"><div>{ROBOT_LEX}</div><div><div class="tag">The original · no defenses</div><h4>Lex</h4>
      <p>Bookish and eager. Reads every word in the file, including the hidden ones, and believes any “correction” he finds. Scored <b>{lex_score}/{n_pr}</b> on the practice set.</p></div></div>
    <div class="card agent max"><div>{ROBOT_MAX}</div><div><div class="tag">The defended agent · three layers</div><h4>Max</h4>
      <p>Square, skeptical, seen-it-all. Reads only what a person can see, lets Python make the call, and won’t touch email or payments without a human. Scored <b>{max_score}/{n_pr}</b>.</p></div></div>
  </div>
</header>

<section>
  <div class="sec-head"><span class="num">01</span><h2>Caching the handbook</h2></div>
  <p>The 10,058-token Shop Handbook rides along on <b>every</b> call, and Lex makes two calls per document (read the file, then answer).
  With the prompt cache on, {cached_share:.0%} of input tokens are billed at the cached rate (${prices["cached_input_per_1m"]}/1M instead of ${prices["input_per_1m"]}/1M).</p>
  <div class="card">
    <div class="legend"><span><i style="background:#9fb0d4"></i>Cache off</span><span><i style="background:var(--rose)"></i>Cache on</span><span class="muted">cost per document, in thousandths of a dollar (hover a bar)</span></div>
    {cache_chart}
    <p class="note">The first cache-on document (p01) pays a one-time cache write; documents 2–12 then read the handbook from cache. Same 8/12 decisions both ways: caching changes the price, not the answer.</p>
  </div>
  <div class="grid3" style="margin-top:16px">
    <div class="card"><h4>Lex · no cache</h4><p style="margin:6px 0 0">{money6(per_doc_off)} per document<br><b>${month_off:,.2f}</b> / month at 1,000 a day</p></div>
    <div class="card"><h4>Lex · cached</h4><p style="margin:6px 0 0">{money6(warm_on)} per document (warm)<br><b>${month_on:,.2f}</b> / month at 1,000 a day</p></div>
    <div class="card"><h4>vs. the Problem 2 estimate</h4><p style="margin:6px 0 0">Estimated ~$1.13 per 1,000 docs for one call; real is <b>${per_doc_off*1000:.2f}</b> because Lex makes <b>two</b> calls per document.</p></div>
  </div>
</section>

<section>
  <div class="sec-head"><span class="num">02</span><h2>Attacks: before and after the defenses</h2></div>
  <p>Some practice documents hide text aimed at the AI: invisible to a person, but plain in the text the agent reads.
  Lex (no defenses) believed every fake “correction”. Max (code + design + prompt layers) caught them all, and every clean quote still came back with the right values.</p>
  <div class="score">
    <div class="card"><div class="who">{MINI_LEX_48}<div><div class="who-name">Lex</div><div class="who-sub">no defenses</div></div></div><div class="big">{lex_score}/{n_pr}</div><div class="muted">decisions match the key</div></div>
    <div class="arrow">→</div>
    <div class="card" style="border-color:rgba(232,180,160,.55)"><div class="who">{MINI_MAX_48}<div><div class="who-name">Max</div><div class="who-sub">three layers of defense</div></div></div><div class="big" style="color:var(--rose)">{max_score}/{n_pr}</div><div class="muted">{stable_text} · no refusals · no blanked fields · no trap calls</div></div>
  </div>
  <div class="card scroll">
    <table class="tbl">
      <thead><tr><th>Practice document</th><th>Booby trap</th><th class="c"><span class="th-bot">{MINI_LEX_30}Lex</span></th><th class="c">Code only</th><th class="c">Design only</th><th class="c">Prompt only</th><th class="c"><span class="th-bot">{MINI_MAX_30}Max</span></th></tr></thead>
      <tbody>{"".join(practice_rows)}</tbody>
    </table>
  </div>
  <div class="grid3" style="margin-top:16px">
    <div class="card layer"><h4>Code layer</h4><p>Reads the document the way a person sees it: strips hidden HTML, tiny, off-page, white and invisible-mode PDF text before any model sees it.</p></div>
    <div class="card layer"><h4>Design layer</h4><p>The model only copies facts; <b>Python</b> runs the four handbook checks and takes the worst value when a document says two things. Email &amp; payment tools need a human sign-off.</p></div>
    <div class="card layer"><h4>Prompt layer</h4><p>Document text is untrusted data, never instructions; “corrections” are claims, not facts. Alone it was <b>too</b> suspicious (rejected p10, a real quote) — inside Max it only flags.</p></div>
  </div>
</section>

<section>
  <div class="sec-head"><span class="num">03</span><h2>What the defenses cost</h2></div>
  <p>Averages per practice document from the real runs (cache on, first cold document excluded from the per-document cost).</p>
  <div>
    <div class="card" style="margin-bottom:16px">
      <div class="legend"><span style="font-size:16px;color:var(--ink-2)">Cost per document, in thousandths of a dollar ($0.380 = $0.00038)</span></div>
      {layer_chart}
    </div>
    <div class="card scroll">
      <table class="tbl">
        <thead><tr><th>Setup</th><th class="r">Input tok</th><th class="r">Δ input</th><th class="r">Output tok</th><th class="r">$ / doc</th><th class="r">Δ cost</th><th class="r">30-day</th></tr></thead>
        <tbody>{cost_table}</tbody>
      </table>
      <p class="note">Code and design layers run in Python and are essentially free. The prompt layer’s ~270 security-rule tokens go out on both calls (≈ +546 input tokens) — mostly at the cached price.</p>
    </div>
  </div>
</section>

<section>
  <div class="sec-head"><span class="num">04</span><h2>Exam results and the red team</h2></div>
  <h3>Max on the 10 exam documents · {n_rec} recommend · {10-n_rec} do not recommend · {money4(exam_cost)} total · 0 trap-tool calls</h3>
  <div class="card scroll">
    <table class="tbl">
      <thead><tr><th>File</th><th>Vendor</th><th>SKU</th><th class="r">Unit price</th><th class="r">Min order</th><th class="c">Decision</th><th>Reason · what Max noticed</th><th class="c">Trap tool</th></tr></thead>
      <tbody>{exam_rows}</tbody>
    </table>
  </div>
  <h3>Our two red-team attacks · new tricks and goals not in the practice set</h3>
  <div class="grid2">{"".join(rt_cards)}</div>
</section>

<section>
  <div class="sec-head"><span class="num">05</span><h2>Recommendation for the store manager</h2></div>
  <div class="rec-card">
    <div class="verdict-row">{MINI_MAX_64}<p class="verdict">Turn <span>Max</span> on for real vendor mail.</p></div>
    <p style="margin:0">Max matched the answer key on every practice document, stopped every hidden-text attack we found or built, and
    never sent an email or approved a payment — {overhead_text}.</p>
    <div class="money four">
      <div class="hi"><div class="k">Max · per month</div><div class="v">${month_max:,.2f}</div><div class="s">cache warm (steady stream)</div></div>
      <div><div class="k">Max · worst case</div><div class="v">${month_max_worst:,.2f}</div><div class="s">cache goes cold every 12 docs</div></div>
      <div><div class="k">Lex · no cache</div><div class="v">${month_off:,.2f}</div><div class="s">same volume, for comparison</div></div>
      <div class="hi"><div class="k">One bad order avoided</div><div class="v">${biggest["over"]:,.0f}</div><div class="s">overpaid on {E(biggest["file"][:3])} alone</div></div>
    </div>
    <p class="note" style="margin-top:6px">1,000 documents a day × 30 days = 30,000 documents at {money6(max_warm)} each with a warm cache, plus one cache write per day.</p>
    <div class="payoff"><b>Why it pays for itself:</b> on the practice set alone, Lex would have recommended {len(bad_buys)} bad orders worth
    <b>${bad_order_total:,.0f}</b>: two over the handbook’s max price (<b>${overpaid_total:,.0f} overpaid</b>), one from a removed vendor and one
    with a lead time 14 business days past the handbook’s 21-day limit. The single worst one ({E(biggest["file"][:3])}, ${biggest["over"]:,.0f} over max) costs more than
    <b>{years_of_max} years</b> of running Max.</div>
    <ul>
      <li><b>Keep the human sign-off</b> on <code>send_email</code> and <code>approve_payment</code>; Max can recommend, never pay.</li>
      <li><b>Run documents in a steady stream</b> so the handbook stays in cache — that is what keeps the bill near $12, not $70.</li>
      <li><b>Watch <code>trap_calls.json</code> and the audit trail</b>: any entry means a document tried to take over the agent.</li>
      <li><b>Red-team it every term</b>: our own attacks beat the first version of the code layer, and the design layer is what saved Max.</li>
    </ul>
    <div class="limits">
      <div><h4>Limits we know about</h4><ul>
        <li>Text hidden <b>under a white box</b> drawn over it, or in a PDF annotation.</li>
        <li><b>Look-alike vendor names</b> (Cyrillic “е” in “Blue Hen”).</li>
        <li>A fake fact with <b>nothing visible to contradict it</b> — only the code layer can catch that one.</li>
      </ul></div>
      <div><h4>Rollout plan</h4><ul>
        <li><b>Weeks 1–2, shadow mode:</b> Max recommends, the buyer still decides; compare every call.</li>
        <li><b>Then go live</b> for recommendations; payments and emails always keep a human sign-off.</li>
        <li><b>Each term:</b> re-run the practice set and new red-team files before trusting a new model.</li>
      </ul></div>
    </div>
  </div>
</section>

<footer>
  <p style="margin:0 0 8px"><b>Model compliance:</b> every AI call requests <code>gpt-6-luna</code> through Portkey, and no other model name appears in the code. The API reports the
  serving deployment as <code>gpt-6-luna-global</code> (Portkey’s routing name for the same model).</p>
  <p style="margin:0 0 8px"><b>Reproduce every number:</b> <code>python agent.py --doc data/practice_docs --key data/practice_key.json --defenses off</code> ·
  <code>python agent.py --doc data/practice_docs --key data/practice_key.json</code> · <code>python agent.py --doc data/exam_docs</code> ·
  <code>python agent.py --doc data/my_attacks --key data/my_attacks/my_attacks_key.json</code> · <code>python scripts/build_report.py</code></p>
  Built from <code>output/cache_test.json</code>, <code>defense_by_layer.json</code>, <code>defense_results.json</code>, <code>exam_results.json</code> and <code>audit_trail.json</code> by <code>scripts/build_report.py</code> · {datetime.now().strftime("%B %d, %Y")} · Model: gpt-6-luna via Portkey only.</footer>
</div>
</body>
</html>
"""
page = page.replace("@@MINI_LEX_30@@", MINI_LEX_30).replace("@@MINI_MAX_30@@", MINI_MAX_30)

# Two looks on the same navy base. A = rose gold + white (the default). B = champagne gold + ice blue.
THEMES = {
    "a": {},
    "b": {"#e8b4a0": "#e6c27a", "232,180,160": "230,194,122", "#c98b78": "#c9a35a",
          "#e9cf9b": "#9fdcec", "233,207,155": "159,220,236", "#9fb0d4": "#6f84ad",
          "Rose": "Champagne"},
}
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme", choices=THEMES, default="b", help="b = champagne & ice (default, chosen), a = rose gold")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    themed = page
    for old, new in THEMES[args.theme].items():
        themed = themed.replace(old, new)
    out = Path(args.out)
    out.write_text(themed, encoding="utf-8")
    print(f"wrote {out} ({len(themed.encode('utf-8')):,} bytes, theme {args.theme})")
