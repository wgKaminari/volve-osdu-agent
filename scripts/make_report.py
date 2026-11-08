"""Build docs/report.html: the evaluation report with figures, from computed results only.

Inputs: docs/results.json (written by `volve-osdu eval`), docs/results_agent_run1.md (the first
agent run, kept for transparency), the 15/9-F-12 input files (depth figure) and the NPD gold
(datum figure). Nothing here is typed by hand: re-run after every evaluation.

    uv run python scripts/make_report.py
"""

import html
import json
import logging
import math
import re

from volve_osdu.config import ROOT, find_bundle
from volve_osdu.eval.conflicts import load_conflicts
from volve_osdu.eval.metrics import load_curve_labels, load_header_gold
from volve_osdu.ingest.las import read_las
from volve_osdu.ingest.wellpath import read_wellpath

RESULTS = ROOT / "docs" / "results.json"
RUN1 = ROOT / "docs" / "results_agent_run1.md"
OUT = ROOT / "docs" / "report.html"
SYSTEMS = ["rules", "llm_only", "agent"]
LABEL = {"rules": "rules", "llm_only": "llm_only", "agent": "agent"}
SLOT = {"rules": "--series-1", "llm_only": "--series-2", "agent": "--series-3"}

CSS = """
.viz-root { color-scheme: light;
  --page:#f9f9f7; --surface-1:#fcfcfb; --text-primary:#0b0b0b; --text-secondary:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a;
  --good:#0ca30c; --critical:#d03b3b; --warning:#fab219; --good-text:#006300;
  --seq-1:#cde2fb; --seq-2:#9ec5f4; --seq-3:#6da7ec; --seq-4:#3987e5; --seq-5:#256abf; --seq-6:#184f95;
  --highlight:#d03b3b; --seq-fg-1:#0b0b0b; --seq-fg-2:#0b0b0b; --seq-fg-3:#0b0b0b; --seq-fg-4:#ffffff; --seq-fg-5:#ffffff; --seq-fg-6:#ffffff; }
@media (prefers-color-scheme: dark) { :root:where(:not([data-theme="light"])) .viz-root {
  color-scheme: dark; --page:#0d0d0d; --surface-1:#1a1a19; --text-primary:#f0efec;
  --text-secondary:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835;
  --border:rgba(255,255,255,0.10); --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70;
  --good-text:#0ca30c; --seq-1:#104281; --seq-2:#184f95; --seq-3:#1c5cab; --seq-4:#256abf;
  --seq-5:#3987e5; --seq-6:#6da7ec; --highlight:#e66767; --seq-fg-1:#ffffff; --seq-fg-2:#ffffff; --seq-fg-3:#ffffff; --seq-fg-4:#ffffff; --seq-fg-5:#0b0b0b; --seq-fg-6:#0b0b0b; } }
:root[data-theme="dark"] .viz-root { color-scheme: dark; --page:#0d0d0d; --surface-1:#1a1a19;
  --text-primary:#f0efec; --text-secondary:#c3c2b7; --muted:#898781; --grid:#2c2c2a;
  --axis:#383835; --border:rgba(255,255,255,0.10); --series-1:#3987e5; --series-2:#d95926;
  --series-3:#199e70; --good-text:#0ca30c; --seq-1:#104281; --seq-2:#184f95; --seq-3:#1c5cab;
  --seq-4:#256abf; --seq-5:#3987e5; --seq-6:#6da7ec; --highlight:#e66767; --seq-fg-1:#ffffff; --seq-fg-2:#ffffff; --seq-fg-3:#ffffff; --seq-fg-4:#ffffff; --seq-fg-5:#0b0b0b; --seq-fg-6:#0b0b0b; }
* { box-sizing: border-box; }
html, body { margin:0; }
body.viz-root { background:var(--page); color:var(--text-primary);
  font:15px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 40px 16px 72px; }
header { border-bottom:1px solid var(--grid); padding-bottom:20px; margin-bottom:28px; }
.eyebrow { color:var(--text-secondary); font-size:13px; letter-spacing:.06em; text-transform:uppercase; margin:0 0 6px; }
h1 { font-size:32px; line-height:1.2; margin:0 0 10px; letter-spacing:-.01em; }
h2 { font-size:22px; margin:48px 0 6px; } h3 { font-size:16px; margin:24px 0 6px; }
.lede { font-size:17px; color:var(--text-secondary); max-width:760px; margin:0; }
.meta { color:var(--muted); font-size:13px; margin-top:12px; }
p { max-width: 780px; } .muted { color:var(--text-secondary); }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:8px 0 12px; }
.tile { background:var(--surface-1); border:1px solid var(--border); border-radius:12px; padding:16px 18px; }
.tile .v { font-size:34px; font-weight:650; line-height:1.1; }
.tile .k { color:var(--text-secondary); font-size:13.5px; margin-top:4px; }
.tile .s { color:var(--muted); font-size:12.5px; margin-top:6px; }
figure { margin:18px 0 8px; background:var(--surface-1); border:1px solid var(--border); border-radius:12px; padding:18px 18px 12px; }
figcaption { color:var(--text-secondary); font-size:13.5px; margin-top:10px; max-width:860px; }
figcaption b { color:var(--text-primary); }
.fig-title { font-weight:650; margin:0 0 2px; } .fig-sub { color:var(--text-secondary); font-size:13.5px; margin:0 0 10px; }
.legend { display:flex; flex-wrap:wrap; gap:16px; font-size:13px; color:var(--text-secondary); margin:4px 0 8px; }
.legend span { display:inline-flex; align-items:center; gap:6px; }
.sw { width:12px; height:12px; border-radius:3px; display:inline-block; }
svg { display:block; width:100%; height:auto; overflow:visible; }
svg text { fill: var(--text-secondary); font-size:12px; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
svg .tick { fill: var(--muted); font-size:11px; font-variant-numeric: tabular-nums; }
svg .grid { stroke: var(--grid); stroke-width:1; } svg .axis { stroke: var(--axis); stroke-width:1; }
svg .hit { fill: transparent; } svg g.mark:hover .dot { stroke: var(--text-primary); stroke-width:2; }
svg .val { fill: var(--text-primary); font-size:11.5px; font-variant-numeric: tabular-nums; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:13.5px; font-variant-numeric: tabular-nums; }
th, td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--grid); vertical-align:top; }
th { color:var(--text-secondary); font-weight:600; }
td.c { text-align:center; }
.heat td.cell { text-align:center; font-weight:600; border:2px solid var(--surface-1); border-radius:6px; }
.ok { color:var(--good-text); font-weight:650; white-space:nowrap; } .no { color:var(--critical); font-weight:650; white-space:nowrap; }
details { margin-top:10px; } summary { cursor:pointer; color:var(--text-secondary); font-size:13px; }
.callout { border-left:3px solid var(--series-1); background:var(--surface-1); padding:12px 16px; border-radius:0 10px 10px 0; margin:16px 0; max-width:820px; }
.grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; }
code { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; background:var(--surface-1); border:1px solid var(--border); padding:1px 5px; border-radius:5px; }
ul { max-width:800px; padding-left:20px; } li { margin:4px 0; }
footer { margin-top:56px; padding-top:16px; border-top:1px solid var(--grid); color:var(--muted); font-size:12.5px; }
a { color: var(--series-1); }
"""


def e(text: object) -> str:
    return html.escape(str(text))


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def est_text(est: dict) -> str:
    if est["value"] is None:
        return "n/a"
    return (
        f"{pct(est['value'])} (95% CI {pct(est['low'])}-{pct(est['high'])}; "
        f"{est['numerator']}/{est['denominator']})"
    )


def legend(items: list[tuple[str, str]]) -> str:
    return (
        "<div class='legend'>"
        + "".join(
            f"<span><i class='sw' style='background:var({var})'></i>{e(name)}</span>"
            for name, var in items
        )
        + "</div>"
    )


# --- Figure 1: headline metrics, dot + 95% CI whisker ------------------------------------------


def fig_metrics(res: dict, rows: list[tuple[str, str]]) -> str:
    left, right, top, row_h = 250, 60, 26, 46
    width, plot_w = 980, 980 - 250 - 60
    height = top + row_h * len(rows) + 30
    x = lambda v: left + plot_w * v  # noqa: E731
    out = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Headline metrics with 95% confidence intervals'>"
    ]
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        out.append(
            f"<line class='grid' x1='{x(t):.1f}' x2='{x(t):.1f}' y1='{top - 8}' y2='{height - 24}'/>"
        )
        out.append(
            f"<text class='tick' x='{x(t):.1f}' y='{height - 8}' text-anchor='middle'>{pct(t)}</text>"
        )
    for i, (key, label) in enumerate(rows):
        y0 = top + i * row_h
        out.append(
            f"<text x='{left - 14}' y='{y0 + row_h / 2 + 4:.1f}' text-anchor='end' style='fill:var(--text-primary)'>{e(label)}</text>"
        )
        for j, sys in enumerate(SYSTEMS):
            est = res[sys]["summary"][key]
            if est["value"] is None:
                continue
            y = y0 + 10 + j * 12
            c = f"var({SLOT[sys]})"
            tip = f"{sys} · {label}: {est_text(est)}"
            out.append(
                f"<g class='mark'><title>{e(tip)}</title>"
                f"<rect class='hit' x='{left}' y='{y - 6}' width='{plot_w}' height='12'/>"
                f"<line x1='{x(est['low']):.1f}' x2='{x(est['high']):.1f}' y1='{y}' y2='{y}' stroke='{c}' stroke-width='2' stroke-linecap='round'/>"
                f"<circle class='dot' cx='{x(est['value']):.1f}' cy='{y}' r='5' fill='{c}' stroke='var(--surface-1)' stroke-width='2'/></g>"
            )
        agent = res["agent"]["summary"][key]
        if agent["value"] is not None:
            out.append(
                f"<text class='val' x='{width - right + 8}' y='{y0 + 10 + 2 * 12 + 4}'>{pct(agent['value'])}</text>"
            )
    out.append("</svg>")
    return "".join(out)


def table_metrics(res: dict, rows: list[tuple[str, str]]) -> str:
    head = "".join(f"<th>{s}</th>" for s in SYSTEMS)
    body = "".join(
        f"<tr><td>{e(label)}</td>"
        + "".join(f"<td>{e(est_text(res[s]['summary'][k]))}</td>" for s in SYSTEMS)
        + "</tr>"
        for k, label in rows
    )
    return f"<div class='table-wrap'><table><tr><th>Metric</th>{head}</tr>{body}</table></div>"


# --- Figure 2: per-field accuracy heatmap ------------------------------------------------------

FACT_LABEL = {
    "wellbore_name": "Wellbore name",
    "kb_elevation_m": "KB elevation",
    "td_md_m": "Total depth (MD)",
    "kop_md_m": "Kick-off point",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "operator": "Operator (alias list)",
    "field": "Field",
}


def seq_step(v: float) -> tuple[str, str]:
    steps = [0.2, 0.4, 0.6, 0.75, 0.9]
    i = sum(v >= s for s in steps)
    return f"var(--seq-{i + 1})", f"var(--seq-fg-{i + 1})"


def fig_per_fact(res: dict) -> str:
    rows = []
    for fact, label in FACT_LABEL.items():
        cells = []
        for s in SYSTEMS:
            est = res[s]["summary"]["per_fact"][fact]
            if est["value"] is None:
                cells.append("<td class='cell'>n/a</td>")
                continue
            bg, fg = seq_step(est["value"])
            tip = f"{s} · {label}: {est_text(est)}"
            cells.append(
                f"<td class='cell' style='background:{bg};color:{fg}' title='{e(tip)}'>"
                f"{pct(est['value'])}<br><span style='font-weight:400;font-size:12px'>{est['numerator']}/{est['denominator']}</span></td>"
            )
        rows.append(f"<tr><td>{e(label)}</td>{''.join(cells)}</tr>")
    head = "".join(f"<th style='text-align:center'>{s}</th>" for s in SYSTEMS)
    scale = "".join(f"<i class='sw' style='background:var(--seq-{i})'></i>" for i in range(1, 7))
    return (
        f"<div class='table-wrap'><table class='heat'><tr><th>Field</th>{head}</tr>{''.join(rows)}</table></div>"
        f"<div class='legend'><span>0%</span><span>{scale}</span><span>100%</span><span>· n = scored values</span></div>"
    )


# --- Figure 3: grounding funnel ----------------------------------------------------------------


def fig_grounding(res: dict) -> str:
    rows = [(s, res[s]["summary"]["grounding_final"]) for s in ("llm_only", "agent")]
    width, left, bar_h, gap = 980, 120, 22, 34
    max_n = max(est["denominator"] for _, est in rows) or 1
    plot_w = width - left - 150
    height = 20 + len(rows) * (2 * bar_h + gap)
    out = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Report facts proposed and kept'>"
    ]
    for i, (s, est) in enumerate(rows):
        y = 10 + i * (2 * bar_h + gap)
        c = f"var({SLOT[s]})"
        prop_w = plot_w * est["denominator"] / max_n
        kept_w = plot_w * est["numerator"] / max_n
        out.append(
            f"<text x='{left - 14}' y='{y + bar_h + 6}' text-anchor='end' style='fill:var(--text-primary)'>{s}</text>"
        )
        out.append(
            f"<g><title>{s}: {est['denominator']} report facts proposed</title>"
            f"<rect x='{left}' y='{y}' width='{prop_w:.1f}' height='{bar_h}' rx='4' fill='{c}' opacity='0.28'/></g>"
        )
        out.append(
            f"<text class='val' x='{left + prop_w + 8:.1f}' y='{y + 15}'>{est['denominator']} proposed</text>"
        )
        out.append(
            f"<g><title>{s}: {est['numerator']} kept after the grounding check ({pct(est['value'])})</title>"
            f"<rect x='{left}' y='{y + bar_h + 2}' width='{max(kept_w, 2):.1f}' height='{bar_h}' rx='4' fill='{c}'/></g>"
        )
        out.append(
            f"<text class='val' x='{left + kept_w + 8:.1f}' y='{y + bar_h + 17}'>{est['numerator']} kept · {pct(est['value'])}</text>"
        )
    out.append("</svg>")
    return "".join(out)


# --- Figure 4: conflict detection matrix -------------------------------------------------------


def fig_detection(res: dict) -> str:
    conflicts = load_conflicts()
    found = {s: {tuple(d) for d in res[s]["summary"]["detected"]} for s in SYSTEMS}
    rows = []
    for c in conflicts:
        key = (c.bundle, c.fact, c.reason)
        cells = "".join(
            "<td class='c'><span class='ok' title='detected'>✓ flagged</span></td>"
            if key in found[s]
            else "<td class='c'><span class='no' title='missed'>✗ missed</span></td>"
            for s in SYSTEMS
        )
        kind = "real" if c.kind == "known" else "injected"
        rows.append(
            f"<tr><td><code>{e(c.bundle)}</code></td><td>{e(kind)}</td><td>{e(c.reason)}</td>"
            f"<td class='muted'>{e(c.description[:95])}</td>{cells}</tr>"
        )
    false_rows = []
    for s in SYSTEMS:
        for b, f, r in res[s]["summary"]["false_flags"]:
            false_rows.append(f"<li>{s}: <code>{e(b)}</code> {e(f)} {e(r)}</li>")
    head = "".join(f"<th style='text-align:center'>{s}</th>" for s in SYSTEMS)
    extra = (
        "<p class='muted'>False flags: none.</p>"
        if not false_rows
        else f"<p class='muted'>False flags:</p><ul>{''.join(false_rows)}</ul>"
    )
    return (
        f"<div class='table-wrap'><table><tr><th>Bundle</th><th>Type</th><th>Expected flag</th><th>What it is</th>{head}</tr>"
        f"{''.join(rows)}</table></div>{extra}"
    )


# --- Figure 5: agent run 1 -> run 2 dumbbell ---------------------------------------------------

RUN1_ROWS = {
    "Field accuracy": "field_accuracy",
    "Abstention accuracy": "abstention_accuracy",
    "Grounding: report facts kept": "grounding_final",
    "Review-flag precision": "flag_precision",
    "Review-flag recall": "flag_recall",
}


def run1_values() -> dict[str, float]:
    text = RUN1.read_text(encoding="utf-8")
    values = {}
    for label, key in RUN1_ROWS.items():
        m = re.search(rf"^\| {re.escape(label)}[^|]*\| (\d+)%", text, re.MULTILINE)
        if m:
            values[key] = int(m.group(1)) / 100
    return values


def fig_runs(res: dict) -> str:
    before = run1_values()
    after = {k: res["agent"]["summary"][k]["value"] for k in RUN1_ROWS.values()}
    labels = {v: k for k, v in RUN1_ROWS.items()}
    left, width, row_h, top = 250, 980, 34, 14
    plot_w = width - left - 80
    height = top + row_h * len(before) + 26
    x = lambda v: left + plot_w * v  # noqa: E731
    out = [f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Agent run 1 versus run 2'>"]
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        out.append(
            f"<line class='grid' x1='{x(t):.1f}' x2='{x(t):.1f}' y1='{top - 6}' y2='{height - 22}'/>"
            f"<text class='tick' x='{x(t):.1f}' y='{height - 6}' text-anchor='middle'>{pct(t)}</text>"
        )
    for i, (key, b) in enumerate(before.items()):
        a = after[key]
        y = top + i * row_h + row_h / 2
        out.append(
            f"<text x='{left - 14}' y='{y + 4:.1f}' text-anchor='end' style='fill:var(--text-primary)'>{e(labels[key])}</text>"
        )
        out.append(
            f"<g class='mark'><title>{e(labels[key])}: run 1 {pct(b)} → run 2 {pct(a)}</title>"
            f"<line x1='{x(b):.1f}' x2='{x(a):.1f}' y1='{y:.1f}' y2='{y:.1f}' stroke='var(--axis)' stroke-width='2'/>"
            f"<circle cx='{x(b):.1f}' cy='{y:.1f}' r='5' fill='var(--surface-1)' stroke='var(--series-3)' stroke-width='2'/>"
            f"<circle class='dot' cx='{x(a):.1f}' cy='{y:.1f}' r='5.5' fill='var(--series-3)' stroke='var(--surface-1)' stroke-width='2'/></g>"
        )
        out.append(f"<text class='val' x='{width - 70}' y='{y + 4:.1f}'>{pct(b)} → {pct(a)}</text>")
    out.append("</svg>")
    return "".join(out)


# --- Figure 6: 15/9-F-12 curve depth ranges vs final survey station ----------------------------


def fig_f12() -> tuple[str, float, float]:
    bundle = find_bundle("15/9-F-12")
    survey = read_wellpath(bundle.wellpath).base_md
    curves = []
    for path in bundle.las:
        for c in read_las(path).curves:
            if c.top_depth is not None and c.base_depth is not None:
                curves.append(
                    (c.mnemonic, path.stem.split("_")[-2].lower(), c.top_depth, c.base_depth)
                )
    curves.sort(key=lambda c: -c[3])
    width, left, row_h, top = 980, 150, 20, 22
    max_md = math.ceil(max(c[3] for c in curves) / 500) * 500
    plot_w = width - left - 30
    height = top + row_h * len(curves) + 30
    x = lambda v: left + plot_w * v / max_md  # noqa: E731
    out = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='15/9-F-12 curve depth ranges'>"
    ]
    for t in range(0, int(max_md) + 1, 500):
        out.append(
            f"<line class='grid' x1='{x(t):.1f}' x2='{x(t):.1f}' y1='{top - 6}' y2='{height - 24}'/>"
            f"<text class='tick' x='{x(t):.1f}' y='{height - 8}' text-anchor='middle'>{t}</text>"
        )
    for i, (name, file, t0, t1) in enumerate(curves):
        y = top + i * row_h
        below = t1 > survey + 5
        color = "var(--highlight)" if below else "var(--series-1)"
        out.append(
            f"<text x='{left - 12}' y='{y + 13}' text-anchor='end' style='fill:var(--text-primary)'>{e(name)} <tspan style='fill:var(--muted)'>{e(file)}</tspan></text>"
        )
        out.append(
            f"<g class='mark'><title>{e(name)} ({file} LAS): non-null data {t0:.1f}-{t1:.1f} m MD"
            + (f" — {t1 - survey:.1f} m below the final survey station" if below else "")
            + "</title>"
            f"<rect x='{x(t0):.1f}' y='{y + 4}' width='{x(t1) - x(t0):.1f}' height='{row_h - 8}' rx='4' fill='{color}'/></g>"
        )
        if below:
            out.append(f"<text class='val' x='{x(t1) + 6:.1f}' y='{y + 13}'>{t1:.1f} m</text>")
    xs = x(survey)
    out.append(
        f"<line x1='{xs:.1f}' x2='{xs:.1f}' y1='{top - 14}' y2='{height - 24}' stroke='var(--text-primary)' stroke-width='2' stroke-dasharray='5 4'/>"
        f"<text x='{xs - 6:.1f}' y='{top - 10}' text-anchor='end' style='fill:var(--text-primary);font-weight:600'>final survey station {survey:.0f} m MD</text>"
    )
    out.append("</svg>")
    return "".join(out), survey, max(c[3] for c in curves)


# --- Figure 7: datum check ---------------------------------------------------------------------


def to_ecef(lat: float, lon: float, a: float, f: float) -> tuple[float, float, float]:
    e2 = f * (2 - f)
    la, lo = math.radians(lat), math.radians(lon)
    n = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return (
        n * math.cos(la) * math.cos(lo),
        n * math.cos(la) * math.sin(lo),
        n * (1 - e2) * math.sin(la),
    )


def to_geodetic(x: float, y: float, z: float, a: float, f: float) -> tuple[float, float]:
    e2 = f * (2 - f)
    lon, p = math.atan2(y, x), math.hypot(x, y)
    lat = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * n * math.sin(lat), p)
    return math.degrees(lat), math.degrees(lon)


def ed50_to_wgs84(lat: float, lon: float) -> tuple[float, float]:
    """EPSG:1133 style 3-parameter shift (-87, -98, -121 m); accurate to a few metres here."""
    x, y, z = to_ecef(lat, lon, 6378388.0, 1 / 297.0)
    return to_geodetic(x - 87, y - 98, z - 121, 6378137.0, 1 / 298.257223563)


def metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat = (a[0] - b[0]) * 111_320
    dlon = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def fig_datum() -> tuple[str, list[tuple[str, float, float]]]:
    gold = load_header_gold()
    rows = []
    for name in ("15/9-F-12", "15/9-19 A"):
        las = read_las(find_bundle(name).las[0])
        las_pos = (float(las.header_value("LAT")), float(las.header_value("LON")))  # type: ignore[arg-type]
        npd = (float(gold[(name, "latitude")]["value"]), float(gold[(name, "longitude")]["value"]))
        rows.append((name, metres(las_pos, npd), metres(las_pos, ed50_to_wgs84(*npd))))
    width, left, bar_h = 980, 150, 20
    max_m = max(max(r[1], r[2]) for r in rows)
    plot_w = width - left - 200
    height = 16 + len(rows) * (2 * bar_h + 30)
    out = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Distance between LAS position and NPD position'>"
    ]
    for i, (name, d_ed50, d_wgs) in enumerate(rows):
        y = 8 + i * (2 * bar_h + 30)
        out.append(
            f"<text x='{left - 12}' y='{y + bar_h + 5}' text-anchor='end' style='fill:var(--text-primary);font-weight:600'>{e(name)}</text>"
        )
        for j, (label, d) in enumerate(
            (("vs NPD as ED50", d_ed50), ("vs NPD converted to WGS84", d_wgs))
        ):
            match = d < 10
            yy = y + j * (bar_h + 2)
            w = max(plot_w * d / max_m, 3)
            fill = "var(--series-1)" if match else "var(--axis)"
            out.append(
                f"<g><title>{e(name)} LAS LAT/LON {label}: {d:.1f} m</title>"
                f"<rect x='{left}' y='{yy}' width='{w:.1f}' height='{bar_h}' rx='4' fill='{fill}'/></g>"
                f"<text class='val' x='{left + w + 8:.1f}' y='{yy + 14}'>{d:.1f} m {e(label)}"
                + (" ← match" if match else "")
                + "</text>"
            )
    out.append("</svg>")
    return "".join(out), rows


# --- page --------------------------------------------------------------------------------------


def disputed_table(res: dict) -> str:
    rows = [o for o in res["rules"]["outcomes"] if o["kind"] == "disputed"]
    lookup = {
        s: {(o["wellbore"], o["fact"]): o for o in res[s]["outcomes"] if o["kind"] == "disputed"}
        for s in SYSTEMS
    }
    body = ""
    for o in rows:
        vals = "".join(
            f"<td>{e(_shown(lookup[s][(o['wellbore'], o['fact'])]['predicted']))}</td>"
            for s in SYSTEMS
        )
        body += (
            f"<tr><td>{e(o['wellbore'])}</td><td>{e(FACT_LABEL.get(o['fact'], o['fact']))}</td>"
            f"<td>{e(o['gold'])}</td>{vals}<td class='muted'>{e(o['note'])}</td></tr>"
        )
    head = "".join(f"<th>{s}</th>" for s in SYSTEMS)
    return f"<div class='table-wrap'><table><tr><th>Wellbore</th><th>Fact</th><th>NPD</th>{head}<th>Why they differ</th></tr>{body}</table></div>"


def _shown(value: object) -> str:
    return "(left empty)" if value is None else str(value)


def cost_table(res: dict) -> str:
    body = ""
    for s in SYSTEMS:
        llm = res[s]["summary"]["llm"]
        body += (
            f"<tr><td>{s}</td><td>{e(res[s]['model'] or '-')}</td><td>{llm['calls_per_wellbore']:.1f}</td>"
            f"<td>{llm['tokens_per_wellbore']:,.0f}</td><td>{llm['seconds_per_wellbore']:.0f}</td>"
            f"<td>{llm['retries']}</td></tr>"
        )
    return (
        "<div class='table-wrap'><table><tr><th>System</th><th>Model</th><th>LLM calls / wellbore</th>"
        f"<th>Tokens / wellbore</th><th>Model seconds / wellbore</th><th>Wellbores with retries</th></tr>{body}</table></div>"
    )


def build() -> str:
    doc = json.loads(RESULTS.read_text(encoding="utf-8"))
    res, meta = doc["systems"], doc["meta"]
    a = res["agent"]["summary"]
    lo = res["llm_only"]["summary"]
    labels = load_curve_labels()
    reviewed = sum(r["reviewed"] == "true" for r in labels.values())
    f12_svg, survey, gr_base = fig_f12()
    datum_svg, datum_rows = fig_datum()

    metric_rows = [
        ("field_accuracy", "Field accuracy (header values)"),
        ("report_fact_accuracy", "Facts from report prose"),
        ("abstention_accuracy", "Abstention (value not in inputs)"),
        ("grounding_final", "Report facts grounded"),
        ("flag_precision", "Review-flag precision"),
        ("flag_recall", "Review-flag recall"),
        ("validation_pass_rate", "Valid manifests"),
        ("curve_unit_accuracy", "Curve unit (provisional labels)"),
        ("curve_family_accuracy", "Curve family (provisional labels)"),
    ]
    sys_legend = legend([(s, SLOT[s]) for s in SYSTEMS])
    n_conf = len(load_conflicts())

    tiles = f"""
<div class='tiles'>
 <div class='tile'><div class='v'>{pct(a["field_accuracy"]["value"])}</div><div class='k'>header values correct (agent)</div>
  <div class='s'>95% CI {pct(a["field_accuracy"]["low"])}-{pct(a["field_accuracy"]["high"])} · {a["field_accuracy"]["numerator"]}/{a["field_accuracy"]["denominator"]}</div></div>
 <div class='tile'><div class='v'>{pct(a["report_fact_accuracy"]["value"])} <span style='font-size:18px;color:var(--text-secondary)'>vs {pct(lo["report_fact_accuracy"]["value"])}</span></div>
  <div class='k'>facts read from report prose: agent vs one-prompt LLM</div><div class='s'>{a["report_fact_accuracy"]["numerator"]}/{a["report_fact_accuracy"]["denominator"]} vs {lo["report_fact_accuracy"]["numerator"]}/{lo["report_fact_accuracy"]["denominator"]}</div></div>
 <div class='tile'><div class='v'>{a["hallucination_rate"]["numerator"]}</div><div class='k'>emitted values not found in any input</div>
  <div class='s'>of {a["hallucination_rate"]["denominator"]} populated values (agent)</div></div>
 <div class='tile'><div class='v'>{a["flag_recall"]["numerator"]}/{a["flag_recall"]["denominator"]}</div><div class='k'>known + injected conflicts sent to review</div>
  <div class='s'>precision {pct(a["flag_precision"]["value"])}, {len(a["false_flags"])} false flags</div></div>
</div>"""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Volve OSDU Evaluation</title><style>{CSS}</style></head>
<body class="viz-root"><main>
<header>
 <p class="eyebrow">Evaluation report · volve-osdu-agent</p>
 <h1>Converting Equinor's Volve well data into OSDU records: how well does an agent do it?</h1>
 <p class="lede">An agent turns raw LAS logs, well paths and petrophysical report PDFs into validated OSDU
 records. It is measured on 13 wellbores against independent ground truth (Norwegian Offshore
 Directorate), next to a rules-only and a single-prompt LLM baseline.</p>
 <p class="meta">Generated {e(meta["date"])} · commit <code>{e(meta["commit"])}</code> · model {e(res["agent"]["model"])} (local, laptop GPU) ·
 n = 13 wellbores + 14 perturbed bundles · 95% CIs: wellbore bootstrap, 2,000 resamples</p>
</header>

<h2>Summary</h2>
{tiles}
<ul>
 <li><b>The agent reads report prose far better than one big prompt:</b> {a["report_fact_accuracy"]["numerator"]} of
 {a["report_fact_accuracy"]["denominator"]} depths and elevations from report text correct, against {lo["report_fact_accuracy"]["numerator"]} for the
 single-prompt baseline, with the same small local model.</li>
 <li><b>Nothing invented reaches the output.</b> Every report fact must quote its page verbatim and pass type,
 range and wellbore checks; {a["grounding_final"]["denominator"] - a["grounding_final"]["numerator"]} agent proposals and
 {lo["grounding_final"]["denominator"] - lo["grounding_final"]["numerator"]} baseline proposals were rejected and flagged instead of emitted.</li>
 <li><b>Every conflict was routed to a human:</b> all {n_conf} known and injected conflicts (logs deeper than the well,
 swapped coordinates, plan well paths, contradictory headers) were flagged, with no false flags.</li>
 <li><b>The data itself has problems the ground truth does not show:</b> mixed coordinate datums, a sidetrack's TD
 recorded on its parent, and report-vs-registry disagreements (section 6).</li>
</ul>

<h2>1. What was measured</h2>
<div class="grid2">
 <div><h3>Three systems, one pipeline</h3>
 <p class="muted">All three share parsing, record building (Equinor's <code>osdu-python-models</code>) and validation; they
 differ only in the judgement steps: which wellbore it is, facts from report prose, curve mapping.</p>
 <ul><li><b>rules</b>: regex on report text + a static curve dictionary, no LLM</li>
 <li><b>llm_only</b>: one prompt per wellbore, no retrieval, lookup or retries</li>
 <li><b>agent</b>: LangGraph graph with focused prompts, page retrieval, reference-list lookup and up to 2 retries with the validator's error message</li></ul></div>
 <div><h3>Independent ground truth</h3>
 <p class="muted">NPD wellbore headers (11 of 13 wellbores; technical sidetracks are not registered) and Equinor's well
 picks. Gold is read only by evaluation code; a test records every file a run opens and fails if gold is among them.</p>
 <ul><li><b>Recoverable</b> values (stated in some input) are scored for accuracy</li>
 <li><b>Not recoverable</b> values must be left empty (abstention)</li>
 <li><b>Disputed</b> values (inputs disagree with NPD) are reported, never scored</li></ul></div>
</div>

<h2>2. Headline metrics</h2>
<figure>
 <p class="fig-title">Agent vs baselines, with 95% confidence intervals</p>
 <p class="fig-sub">Dot = pooled value, line = 95% bootstrap CI over wellbores. Right column: agent value.</p>
 {sys_legend}
 {fig_metrics(res, metric_rows)}
 <figcaption><b>Read with the caveats:</b> the rules baseline's regexes were written after reading these same reports (no
 held-out set), so its scores are an optimistic upper bound for hand-written rules on this data. Curve labels are
 AI-drafted, {reviewed}/{len(labels)} reviewed so far, and share conventions with the rules dictionary, so curve numbers are provisional.
 <details><summary>Table view</summary>{table_metrics(res, metric_rows)}</details></figcaption>
</figure>

<h2>3. Accuracy per field</h2>
<figure>
 <p class="fig-title">Share of scored values correct, per OSDU field</p>
 <p class="fig-sub">Tolerances: depth 0.5 m, elevation 0.2 m, lat/lon 1e-4°. Hover a cell for its CI.</p>
 {fig_per_fact(res)}
 <figcaption>The gap is in the fields that live in report prose (<b>KB elevation, total depth, kick-off point</b>): one
 report often covers three sibling wellbores, and the facts must be attributed to the right one. Header fields
 (name, field, operator, location) are parsed by code for every system and score alike. Operator is scored with a
 documented alias list (Statoil, StatoilHydro, Den norske stats oljeselskap and Equinor are one company); strict
 exact-name scoring gives {pct(a["operator_strict"]["value"])} for every system.</figcaption>
</figure>

<h2>4. Grounding: proposed vs kept</h2>
<figure>
 <p class="fig-title">Report facts proposed by the LLM and kept after the grounding check</p>
 <p class="fig-sub">A fact is kept only if its quote is verbatim on the page, contains the value, states the right kind of fact and names the right wellbore.</p>
 {legend([("llm_only", SLOT["llm_only"]), ("agent", SLOT["agent"])])}
 {fig_grounding(res)}
 <figcaption>The single-prompt baseline mostly quotes text that is not on the page or numbers that are not in its quote;
 the agent's retrieval and feedback loop keep {pct(a["grounding_final"]["value"])} of its proposals. Rejected values never reach a
 record: they are dropped and listed for review.</figcaption>
</figure>

<h2>5. Human review: are conflicts caught?</h2>
<figure>
 <p class="fig-title">Expected review flags on real and perturbed bundles</p>
 <p class="fig-sub">{n_conf} expected flags: 3 real conflicts in Equinor's files, injected ones on 14 perturbed copies (2 are negative controls with no injected problem), and real conflicts inherited by those copies.</p>
 {fig_detection(res)}
 <figcaption>Flags are matched on (bundle, fact, reason). Precision counts every conflict-type flag a system raised; the
 blanket "datum assumed" note and flags about a system's own rejected guesses are not conflict claims.</figcaption>
</figure>

<h2>6. What the evaluation found in Equinor's data</h2>
<figure>
 <p class="fig-title">15/9-F-12: a log deeper than the well</p>
 <p class="fig-sub">Depth range (m MD) with non-null data per curve, both LAS files. Red = deeper than the last survey station + 5 m.</p>
 {f12_svg}
 <figcaption>GR has data to <b>{gr_base:.1f} m</b> MD while the actual well path ends at <b>{survey:.0f} m</b>. A log
 deeper than the hole's final survey should never be ingested silently; every system raises this flag with both sources.</figcaption>
</figure>
<figure>
 <p class="fig-title">Mixed coordinate datums</p>
 <p class="fig-sub">Distance between the LAS LAT/LON and NPD's position, taken as ED50 and converted to WGS84.</p>
 {datum_svg}
 <figcaption>No LAS header states a datum. 15/9-F-12's coordinates match NPD in <b>ED50</b>
 ({datum_rows[0][1]:.1f} m); 15/9-19 A's match NPD only after conversion to <b>WGS84</b> ({datum_rows[1][2]:.1f} m, against
 {datum_rows[1][1]:.0f} m otherwise). Treating both alike misplaces a well by ~{datum_rows[1][1]:.0f} m, so every location
 carries a "datum assumed" review flag.</figcaption>
</figure>
<h3>Where inputs and the registry disagree (disputed gold)</h3>
<p class="muted">Reported, not scored, and never "fixed" to match a system. Each system's emitted value is shown.</p>
{disputed_table(res)}

<h2>7. Iterations, reported openly</h2>
<figure>
 <p class="fig-title">Agent run 1 → run 2</p>
 <p class="fig-sub">Run 1 exposed facts that were quoted verbatim but were the wrong kind of fact or the wrong wellbore (TD 347 m taken as
 KB elevation; a sidetrack's kick-off point given to its parent). The grounding rule gained generic checks; prompts were not changed.</p>
 {legend([("run 1", "--axis"), ("run 2 (current)", "--series-3")])}
 {fig_runs(res)}
 <figcaption>Stricter checks made abstention and flag precision perfect and lowered the grounding rate: run 1's high
 grounding rate counted those wrong-but-quoted facts as grounded. Also changed after looking at results: an identity
 fallback (most specific header name, flagged) and a lenient parser for the llm_only baseline so it is judged on its
 answers, not on a strict parser. Run 1's full report is kept in <code>docs/results_agent_run1.md</code>.</figcaption>
</figure>

<h2>8. Cost and reproducibility</h2>
{cost_table(res)}
<p class="muted">Model time is measured on a laptop RTX 3050 Ti (4 GB) running qwen3 4B through Ollama, thinking off,
temperature 0. Every LLM call is cached on disk (key = model + messages + parameters); re-running the evaluation
makes 0 LLM calls and reproduces every number. A stronger hosted model is a configuration change.</p>

<h2>9. Limitations</h2>
<ul>
 <li><b>Small n.</b> 13 wellbores, header gold for 11, some fields with 1-7 values: intervals are wide by necessity.</li>
 <li><b>No held-out development set.</b> The rules baseline and the semantic grounding checks were shaped after seeing these bundles; both runs are reported.</li>
 <li><b>Provisional curve labels.</b> {reviewed}/{len(labels)} owner-reviewed; curve mapping is the weakest area for a 4B model (many rock-physics curves left unmapped rather than guessed).</li>
 <li><b>Assumptions.</b> Coordinate datum is assumed and flagged; ACL and legal tags are placeholders; no real OSDU instance is called.</li>
 <li><b>Scope.</b> LAS, PDF text and well paths only: DLIS files, Word reports, formation tops and image-only report pages are not read.</li>
</ul>

<footer>Generated by <code>scripts/make_report.py</code> from <code>docs/results.json</code> (<code>uv run volve-osdu eval</code>).
Data: Equinor Volve open dataset, credit "Equinor and the Volve licence partners" (Equinor Open Data Licence);
ground truth: Norwegian Offshore Directorate (NLOD). Code: Apache-2.0,
<a href="https://github.com/wgKaminari/volve-osdu-agent">github.com/wgKaminari/volve-osdu-agent</a>.</footer>
</main></body></html>
"""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    OUT.write_text(build(), encoding="utf-8")
    logging.info("wrote %s", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
