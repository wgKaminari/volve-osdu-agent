"""Render one wellbore run as a self-contained HTML page: inputs -> facts -> flags -> records.

uv run python scripts/make_demo.py outputs/example/15_9-F12 docs/demo/index.html
"""

import html
import json
import logging
import sys
from pathlib import Path

CSS = """
:root { --bg:#fbfaf7; --fg:#1d232b; --muted:#5d6670; --card:#ffffff; --line:#e3e0d8;
  --warn:#9a5b00; --warn-bg:#fff4e0; --block:#a1262b; --block-bg:#fde8e8; --info:#285c8c;
  --info-bg:#e6f0fa; --ok:#2f6b3a; --code:#f3f1ec; --accent:#0b5f6b; }
@media (prefers-color-scheme: dark) { :root { --bg:#14181d; --fg:#e6e8eb; --muted:#9aa3ad;
  --card:#1c2128; --line:#2c333c; --warn:#f0b35a; --warn-bg:#3a2c14; --block:#f08a8e;
  --block-bg:#3b1d20; --info:#8cc0f0; --info-bg:#172a3d; --ok:#8fd19e; --code:#232a32;
  --accent:#6cc5d1; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 28px; margin: 0 0 4px; } h2 { font-size: 19px; margin: 36px 0 12px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.stats { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap:12px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.stat b { display:block; font-size:24px; } .stat span { color:var(--muted); font-size:13px; }
.flag { border-radius:10px; padding:12px 14px; margin:10px 0; border:1px solid var(--line); }
.flag.warn { background:var(--warn-bg); } .flag.block { background:var(--block-bg); }
.flag.info { background:var(--info-bg); }
.sev { font-weight:700; text-transform:uppercase; font-size:12px; letter-spacing:.04em; }
.warn .sev { color:var(--warn); } .block .sev { color:var(--block); } .info .sev { color:var(--info); }
table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line);
  border-radius:10px; overflow:hidden; font-size:14px; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; }
code, pre { font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }
code { background:var(--code); padding:1px 5px; border-radius:4px; overflow-wrap:anywhere; }
pre { background:var(--code); padding:12px; border-radius:8px; overflow:auto; max-height:420px; }
details { background:var(--card); border:1px solid var(--line); border-radius:10px; margin:8px 0;
  padding:8px 12px; } summary { cursor:pointer; font-weight:600; }
.ok { color:var(--ok); font-weight:600; } .muted { color:var(--muted); }
.table-wrap { overflow-x:auto; }
footer { margin-top:40px; color:var(--muted); font-size:13px; }
a { color: var(--accent); }
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def sources(provenance: list[dict]) -> str:
    parts = []
    for p in provenance:
        quote = f'<br><span class="muted">“{esc(p["quote"])}”</span>' if p.get("quote") else ""
        method = esc(p["method"])
        parts.append(
            f"<code>{esc(p['source_file'].rsplit('/', 1)[-1])}</code> {esc(p['locator'])}"
            f" <span class='muted'>({method})</span>{quote}"
        )
    return "<br>".join(parts)


def render(run: Path) -> str:
    validation = json.loads((run / "validation.json").read_text())
    facts = json.loads((run / "facts.json").read_text())
    records = [json.loads(p.read_text()) for p in sorted((run / "records").glob("*.json"))]
    flags, issues = validation["flags"], validation["issues"]
    errors = [i for i in issues if i["severity"] == "error"]
    wellbore = next(r for r in records if r["kind"].startswith("osdu:wks:master-data--Wellbore"))
    name = wellbore["data"]["FacilityName"]
    trace_path = run / "trace.jsonl"
    calls = len(trace_path.read_text().splitlines()) if trace_path.exists() else 0

    out = [
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Volve OSDU review</title><style>{CSS}</style></head><body><main>",
        f"<h1>Wellbore {esc(name)}</h1>",
        "<p class='sub'>Raw Volve files converted to OSDU records by <code>volve-osdu</code>. "
        "Every value below carries its source; anything a human must decide is a review flag.</p>",
        "<div class='stats'>",
        f"<div class='stat'><b>{len(records)}</b><span>OSDU records</span></div>",
        f"<div class='stat'><b>{len(flags)}</b><span>review flags</span></div>",
        f"<div class='stat'><b class='{'ok' if not errors else ''}'>{len(errors)}</b>"
        "<span>validation errors</span></div>",
        f"<div class='stat'><b>{calls}</b><span>LLM calls</span></div></div>",
        "<h2>Review flags</h2>",
    ]
    order = {"block": 0, "warn": 1, "info": 2}
    for flag in sorted(flags, key=lambda f: order[f["severity"]]):
        cands = "".join(
            f"<li><b>{esc(c['value'])}</b> ← {sources(c.get('provenance', []))}</li>"
            for c in flag.get("candidates", [])
        )
        out.append(
            f"<div class='flag {esc(flag['severity'])}'><span class='sev'>{esc(flag['severity'])}"
            f" · {esc(flag['reason'])}</span><div>{esc(flag['message'])}</div>"
            + (f"<ul>{cands}</ul>" if cands else "")
            + "</div>"
        )
    if not flags:
        out.append("<p class='muted'>None.</p>")

    out += [
        "<h2>Facts and where they came from</h2><div class='table-wrap'><table>"
        "<tr><th>Fact</th><th>Value</th><th>Sources</th></tr>"
    ]
    for fact_name, fact in sorted(facts.items()):
        value = (
            "(abstained)"
            if fact.get("value") is None
            else f"{fact['value']} {fact.get('unit') or ''}"
        )
        out.append(
            f"<tr><td>{esc(fact_name)}</td><td>{esc(value)}</td>"
            f"<td>{sources(fact.get('provenance', []))}</td></tr>"
        )
    out.append("</table></div>")

    out.append("<h2>OSDU records (manifest content)</h2>")
    for rec in records:
        kind = rec["kind"].split(":")[2]
        out.append(
            f"<details><summary>{esc(kind)} <span class='muted'>{esc(rec['id'])}</span>"
            f"</summary><pre>{esc(json.dumps(rec['data'], indent=2))}</pre></details>"
        )

    out.append("<h2>Validation</h2>")
    shown = [i for i in issues if i["severity"] != "info"]
    if shown:
        out.append(
            "<div class='table-wrap'><table><tr><th>Rule</th><th>Severity</th><th>Message</th></tr>"
        )
        out += [
            f"<tr><td>{i['rule']}</td><td>{esc(i['severity'])}</td><td>{esc(i['message'])}</td></tr>"
            for i in shown
        ]
        out.append("</table></div>")
    else:
        out.append("<p class='ok'>All records pass the pinned OSDU schemas and rules 1-10.</p>")
    infos = len(issues) - len(shown)
    if infos:
        out.append(f"<p class='muted'>{infos} info notes (e.g. curves left unmapped).</p>")
    out.append(
        "<footer>Data: Equinor Volve open dataset (Equinor Open Data Licence), credit "
        "“Equinor and the Volve licence partners”. Generated by "
        "<a href='https://github.com/wgKaminari/volve-osdu-agent'>volve-osdu-agent</a>."
        "</footer></main></body></html>"
    )
    return "\n".join(out)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    run, target = Path(sys.argv[1]), Path(sys.argv[2])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(run), encoding="utf-8")
    logging.info("wrote %s", target)


if __name__ == "__main__":
    main()
