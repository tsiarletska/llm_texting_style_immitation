#!/usr/bin/env python3
"""Draw the README charts from results/ratings.csv (standard library only).

Writes SVG files to assets/. Each SVG carries its own light and dark colours
(prefers-color-scheme), so it reads on GitHub in either theme.

Usage: python3 code/make_charts.py
"""
import csv, pathlib, statistics
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
ROWS = list(csv.DictReader(open(ROOT / "results" / "ratings.csv", encoding="utf-8")))

SITUATIONS = {
    "coffee_ua": "Coffee invitation", "exam_ua": "Exam question", "heartbroken_ua": "Heartbroken friend",
    "support_en": "Support agent (EN)", "decline_ua": "Refusing a party", "series_ua": "Disagreeing on a series",
    "stress_ua": "Stressed friend", "teacher_ua": "Formal message from a lecturer", "silly_ua": "Silly banter",
    "cooking_ua": "Cooking advice (topic not in data)",
}

STYLE = """<style>
  text { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; fill: #191919; }
  .muted { fill: #666666; } .title { font-size: 15px; font-weight: 600; } .small { font-size: 11px; }
  .axis { stroke: #d0d0d0; stroke-width: 1; } .grid { stroke: #e6e6e6; stroke-width: 1; }
  .s1 { fill: #257de0; } .s1-stroke { stroke: #257de0; }
  .neutral { fill: #a3a3a3; } .neutral-stroke { stroke: #a3a3a3; }
  .s2 { fill: #f47230; }
  .ring { stroke: #ffffff; }
  @media (prefers-color-scheme: dark) {
    text { fill: #efefef; } .muted { fill: #9c9c9c; }
    .axis { stroke: #4a4a4a; } .grid { stroke: #333333; }
    .s1 { fill: #338ced; } .s1-stroke { stroke: #338ced; }
    .neutral { fill: #6b6b6b; } .neutral-stroke { stroke: #6b6b6b; }
    .s2 { fill: #e76624; } .ring { stroke: #0d1117; }
  }
</style>"""


def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


def by(key, filt=lambda r: True):
    d = defaultdict(list)
    for r in ROWS:
        if filt(r):
            d[key(r)].append(int(r["score"]))
    return d


def svg(w, h, body, title, desc):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-labelledby="t d"><title id="t">{title}</title><desc id="d">{desc}</desc>'
            f"{STYLE}{body}</svg>\n")


def bar_chart(name, title, subtitle, data, label_w=230, w=720):
    """Horizontal bars of mean score (1-5 scale), sorted high to low."""
    items = sorted(((k, mean(v), len(v)) for k, v in data.items()), key=lambda x: -x[1])
    top, row, x0, x1 = 64, 30, label_w, w - 70
    h = top + row * len(items) + 34
    sx = lambda v: x0 + (v - 1) / 4 * (x1 - x0)
    b = [f'<text x="0" y="20" class="title">{title}</text>',
         f'<text x="0" y="40" class="muted small">{subtitle}</text>']
    for t in (1, 2, 3, 4, 5):
        b.append(f'<line x1="{sx(t):.1f}" y1="{top - 6}" x2="{sx(t):.1f}" y2="{top + row * len(items)}" class="grid"/>')
        b.append(f'<text x="{sx(t):.1f}" y="{top + row * len(items) + 18}" class="muted small" text-anchor="middle">{t}</text>')
    desc = []
    for i, (k, m, n) in enumerate(items):
        y = top + i * row
        bw = sx(m) - x0
        b.append(f'<text x="{x0 - 10}" y="{y + 15}" text-anchor="end" font-size="13">{k}</text>')
        b.append(f'<path d="M{x0},{y + 5} h{bw - 4:.1f} a4,4 0 0 1 4,4 v8 a4,4 0 0 1 -4,4 h-{bw - 4:.1f} z" class="s1"/>')
        b.append(f'<text x="{x0 + bw + 8:.1f}" y="{y + 15}" font-size="13" font-weight="600">{m:.2f}</text>')
        desc.append(f"{k}: {m:.2f} (n={n})")
    b.append(f'<line x1="{x0}" y1="{top - 6}" x2="{x0}" y2="{top + row * len(items)}" class="axis"/>')
    (OUT / name).write_text(svg(w, h, "".join(b), title, "; ".join(desc)), encoding="utf-8")


def dumbbell(name):
    base = by(lambda r: r["model"], lambda r: r["setting"] == "baseline")
    ex = by(lambda r: r["model"], lambda r: r["setting"] == "examples")
    models = sorted(base, key=lambda m: -(mean(ex[m]) - mean(base[m])))
    w, top, row, x0, x1 = 720, 84, 34, 200, 620
    h = top + row * len(models) + 34
    lo, hi = 2.5, 4.5
    sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    title = "Did giving the model my real messages help?"
    b = [f'<text x="0" y="20" class="title">{title}</text>',
         '<text x="0" y="40" class="muted small">Mean score without examples vs with ~65 of my messages in the prompt</text>',
         f'<circle cx="6" cy="60" r="5" class="neutral"/><text x="16" y="64" class="small">No examples (baseline)</text>',
         f'<circle cx="176" cy="60" r="5" class="s1"/><text x="186" y="64" class="small">With my examples</text>']
    for t in (2.5, 3, 3.5, 4, 4.5):
        b.append(f'<line x1="{sx(t):.1f}" y1="{top - 8}" x2="{sx(t):.1f}" y2="{top + row * len(models) - 10}" class="grid"/>')
        b.append(f'<text x="{sx(t):.1f}" y="{top + row * len(models) + 8}" class="muted small" text-anchor="middle">{t:g}</text>')
    desc = []
    for i, m in enumerate(models):
        y = top + i * row + 6
        a, e = mean(base[m]), mean(ex[m])
        d = e - a
        b.append(f'<text x="{x0 - 14}" y="{y + 4}" text-anchor="end" font-size="13">{m}</text>')
        b.append(f'<line x1="{sx(a):.1f}" y1="{y}" x2="{sx(e):.1f}" y2="{y}" class="neutral-stroke" stroke-width="2"/>')
        b.append(f'<circle cx="{sx(a):.1f}" cy="{y}" r="6" class="neutral ring" stroke-width="2"/>')
        b.append(f'<circle cx="{sx(e):.1f}" cy="{y}" r="6" class="s1 ring" stroke-width="2"/>')
        b.append(f'<text x="{x1 + 30}" y="{y + 4}" font-size="13" font-weight="600">{d:+.2f}</text>')
        desc.append(f"{m}: {a:.2f} -> {e:.2f} ({d:+.2f})")
    (OUT / name).write_text(svg(w, h, "".join(b), title, "; ".join(desc)), encoding="utf-8")


def could_be_real(name):
    cnt = defaultdict(lambda: {"yes": 0, "maybe": 0, "no": 0})
    for r in ROWS:
        cnt[r["model"]][r["could_be_real"]] += 1
    models = sorted(cnt, key=lambda m: -cnt[m]["yes"] / sum(cnt[m].values()))
    w, top, row, x0, x1 = 720, 84, 30, 200, 690
    h = top + row * len(models) + 14
    title = '"Could I have sent this?"'
    b = [f'<text x="0" y="20" class="title">{title}</text>',
         '<text x="0" y="40" class="muted small">Share of replies per model, both settings together</text>']
    lx = 0
    for cls, lab in (("s1", "Yes"), ("neutral", "Maybe"), ("s2", "No")):
        b.append(f'<rect x="{lx}" y="54" width="10" height="10" rx="2" class="{cls}"/><text x="{lx + 15}" y="63" class="small">{lab}</text>')
        lx += 70
    desc = []
    for i, m in enumerate(models):
        y = top + i * row
        c = cnt[m]
        n = sum(c.values())
        x = x0
        b.append(f'<text x="{x0 - 10}" y="{y + 14}" text-anchor="end" font-size="13">{m}</text>')
        for k, cls in (("yes", "s1"), ("maybe", "neutral"), ("no", "s2")):
            sw = c[k] / n * (x1 - x0)
            if sw > 0:
                b.append(f'<rect x="{x:.1f}" y="{y + 3}" width="{max(sw - 2, 0):.1f}" height="16" rx="3" class="{cls}"/>')
                if sw > 34:
                    b.append(f'<text x="{x + sw / 2 - 1:.1f}" y="{y + 15}" text-anchor="middle" font-size="11" '
                             f'font-weight="600" style="fill:#ffffff">{c[k] / n:.0%}</text>')
            x += sw
        desc.append(f"{m}: yes {c['yes']}, maybe {c['maybe']}, no {c['no']}")
    (OUT / name).write_text(svg(w, h, "".join(b), title, "; ".join(desc)), encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    bar_chart("score_by_model.svg", "How much does it sound like me? Mean score by model",
              "296 replies rated blind on a 1-5 scale, both settings together", by(lambda r: r["model"]), label_w=200)
    dumbbell("examples_effect.svg")
    could_be_real("could_be_real.svg")
    bar_chart("score_by_situation.svg", "Which situations were hardest to fake?",
              "Mean score per test situation, all models and settings together",
              by(lambda r: SITUATIONS[r["scenario"]]), label_w=250)
    for r in sorted(by(lambda r: (r["model"], r["setting"])).items()):
        print(f"{r[0][0]:<24} {r[0][1]:<9} {mean(r[1]):.2f} n={len(r[1])}")
    print("charts ->", OUT)
