"""Generate the public demo page (docs/index.html) for GitHub Pages.

Runs the REAL engine on the synthetic statement, freezes the result, and
renders a single self-contained HTML file. The page has no backend and no
file input by design — it can only ever show this synthetic result, so the
"your statement never leaves your computer" promise cannot be violated here.

Re-run after any engine change:  python tools/build_demo_page.py
"""

import html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from refundradar.audit import build_audit, to_dict
from refundradar.complaint import generate_complaint_pack
from refundradar.parser import parse_generic_csv
SAMPLES = ROOT / "samples"
DOCS = ROOT / "docs"
AS_OF = date(2026, 7, 24)  # frozen so the demo numbers are stable

REPO_URL = "https://github.com/Dhanu2626/refundradar"


def build_demo_data():
    txns = parse_generic_csv(SAMPLES / "demo_statement.csv")
    truth = json.loads((SAMPLES / "ground_truth.json").read_text())
    confirmed = {i["ref"] for i in truth["incidents"]
                 if i["is_incident"] and i["refund_date"] is None}
    audit = build_audit(txns, confirmed, as_of=AS_OF)
    pack = generate_complaint_pack(
        audit, "A. Sample Customer", "2626", "sample@example.com")
    return to_dict(audit), pack


def rupee(n) -> str:
    return "₹" + f"{int(float(n)):,}"


STATUS_BADGE = {
    "refunded_late": ("late", "{amt} owed"),
    "never_refunded": ("never", "{amt} and counting"),
    "refunded_on_time": ("ok", "On time"),
    "excluded_genuine_refund": ("info", "Genuine refund — excluded"),
    "needs_confirmation": ("info", "Needs your confirmation"),
    "unsupported_channel": ("info", "Outside the 2019 circular"),
}
STATUS_ORDER = {"refunded_late": 0, "never_refunded": 1, "needs_confirmation": 2,
                "refunded_on_time": 3, "excluded_genuine_refund": 4,
                "unsupported_channel": 5}
CHANNEL_NAMES = {
    "upi_p2m": "UPI person-to-merchant", "upi_p2p": "UPI person-to-person",
    "imps": "IMPS", "atm": "ATM / Micro-ATM cash withdrawal", "pos": "PoS card",
    "ecom": "Card / e-commerce", "nach": "NACH mandate",
}


def incident_rows(audit: dict) -> str:
    rows = []
    for i in sorted(audit["incidents"], key=lambda x: STATUS_ORDER[x["status"]]):
        cls, tmpl = STATUS_BADGE[i["status"]]
        amt = rupee(i["compensation_inr"]) if i["compensation_inr"] else ""
        badge = tmpl.format(amt=amt)
        name = (i["channel_name"] or CHANNEL_NAMES.get(i["channel"])
                or i["channel"] or "payment")
        d = date.fromisoformat(i["date"]).strftime("%d %b %Y")
        rows.append(
            f'<div class="inc"><div class="main">'
            f'<div class="title">{html.escape(name)} · {rupee(i["amount"])} · {d}</div>'
            f'<div class="sub">{html.escape(i["reason"])}</div></div>'
            f'<span class="badge {cls}">{html.escape(badge)}</span></div>'
        )
    return "\n".join(rows)


def render(audit: dict, pack: str) -> str:
    return TEMPLATE.format(
        owed=rupee(audit["total_owed_inr"]),
        stuck=rupee(audit["stuck_amount"]),
        ontime=audit["on_time_count"],
        lines=audit["statement_lines"],
        as_of=date.fromisoformat(audit["as_of"]).strftime("%d %b %Y"),
        incidents=incident_rows(audit),
        pack=html.escape(pack),
        repo=REPO_URL,
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RefundRadar — the payments auditor your bank hopes you never run</title>
<meta name="description" content="RBI requires your bank to pay you Rs.100/day for late refunds on failed payments, automatically. Almost nobody checks. RefundRadar does.">
<style>
  :root {{
    --bg:#f7f6f3; --card:#fff; --ink:#1a1a18; --muted:#6b6a64; --line:#e4e2db;
    --red-bg:#fceaea; --red:#a32d2d; --red-dark:#791f1f; --amber-bg:#faeeda;
    --amber:#854f0b; --green-bg:#eaf3de; --green:#3b6d11; --accent:#185fa5; --radius:10px;
  }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--ink);
         line-height:1.6; padding:0 16px 60px; }}
  .wrap {{ max-width:820px; margin:0 auto; }}
  .banner {{ background:#eef4fb; border-bottom:1px solid #d6e3f2; color:#0c447c;
            text-align:center; font-size:13px; padding:8px 12px; margin:0 -16px 24px; }}
  header.hero {{ text-align:center; padding:28px 0 8px; }}
  .brand {{ font-size:30px; font-weight:600; }}
  .brand span {{ color:var(--accent); }}
  .tag {{ font-size:17px; color:var(--muted); max-width:600px; margin:10px auto 0; }}
  .arrow {{ color:var(--muted); font-size:13px; margin:16px 0 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
          padding:22px; margin:16px 0; }}
  .demo-label {{ display:inline-block; font-size:12px; background:var(--amber-bg); color:var(--amber);
                padding:3px 10px; border-radius:999px; margin-bottom:12px; }}
  .fileinfo {{ font-size:13px; color:var(--muted); margin-bottom:14px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:6px 0 16px; }}
  .stat {{ border-radius:var(--radius); padding:14px 16px; background:var(--bg); }}
  .stat .label {{ font-size:13px; color:var(--muted); }}
  .stat .value {{ font-size:28px; font-weight:600; }}
  .stat.owed {{ background:var(--red-bg); }} .stat.owed .label {{ color:var(--red); }}
  .stat.owed .value {{ color:var(--red-dark); }}
  .inc {{ display:flex; gap:12px; padding:13px 4px; border-top:1px solid var(--line); align-items:center; flex-wrap:wrap; }}
  .inc .main {{ flex:1; min-width:220px; }} .inc .title {{ font-size:15px; }}
  .inc .sub {{ font-size:13px; color:var(--muted); }}
  .badge {{ font-size:12px; padding:3px 10px; border-radius:999px; white-space:nowrap; }}
  .badge.late {{ background:var(--red-bg); color:var(--red); }}
  .badge.never {{ background:var(--amber-bg); color:var(--amber); }}
  .badge.ok {{ background:var(--green-bg); color:var(--green); }}
  .badge.info {{ background:var(--bg); color:var(--muted); }}
  h2 {{ font-size:19px; margin:8px 0 10px; font-weight:600; }}
  .steps {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; }}
  .step {{ font-size:14px; }} .step b {{ display:block; font-size:15px; margin-bottom:3px; }}
  .step .n {{ display:inline-block; width:24px; height:24px; line-height:24px; text-align:center;
             border-radius:50%; background:var(--accent); color:#fff; font-size:13px; margin-bottom:6px; }}
  details {{ margin-top:8px; }} summary {{ cursor:pointer; color:var(--accent); font-size:14px; }}
  pre {{ white-space:pre-wrap; background:var(--bg); border-radius:var(--radius); padding:16px;
        font-size:12.5px; max-height:380px; overflow:auto; margin-top:12px; }}
  .cta {{ text-align:center; }}
  .btn {{ display:inline-block; background:var(--accent); color:#fff; text-decoration:none;
         padding:11px 22px; border-radius:8px; font-size:15px; margin-top:6px; }}
  .trust {{ font-size:14px; color:var(--muted); margin-top:10px; }}
  footer {{ text-align:center; color:var(--muted); font-size:12px; margin-top:30px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="banner">Live demo with <b>synthetic data</b>. This page can't take a file — the real app runs on your own computer.</div>

  <header class="hero">
    <div class="brand">Refund<span>Radar</span></div>
    <p class="tag">When a digital payment fails in India, RBI requires your bank to refund it on time
      <b>and pay you ₹100 for every day it's late — automatically, without you asking.</b>
      Almost nobody checks whether the bank actually did. RefundRadar checks.</p>
    <p class="arrow">↓ Here's a real audit of a sample statement</p>
  </header>

  <div class="card">
    <span class="demo-label">Sample statement · synthetic</span>
    <div class="fileinfo">📄 {lines} transactions read · audited as of {as_of}</div>
    <div class="cards">
      <div class="stat owed"><div class="label">The bank owes this customer</div><div class="value">{owed}</div></div>
      <div class="stat"><div class="label">Stuck refunds</div><div class="value">{stuck}</div></div>
      <div class="stat"><div class="label">Refunds on time</div><div class="value">{ontime}</div></div>
    </div>
    {incidents}
    <details>
      <summary>See the complaint pack it generates →</summary>
      <pre>{pack}</pre>
    </details>
  </div>

  <div class="card">
    <h2>How it works</h2>
    <div class="steps">
      <div class="step"><span class="n">1</span><b>Read</b>Your bank statement export, on your own computer.</div>
      <div class="step"><span class="n">2</span><b>Reconcile</b>Finds failed payments whose refund came late or never.</div>
      <div class="step"><span class="n">3</span><b>Claim</b>Computes what you're owed and writes the complaint letter.</div>
    </div>
  </div>

  <div class="card cta">
    <h2>Run it on your own statement</h2>
    <p class="trust">The full app runs entirely on your machine — no signup, no upload, no server.
      Your statement never leaves your computer. This demo page has no way to receive a file at all.</p>
    <a class="btn" href="{repo}">Get it on GitHub</a>
  </div>

  <footer>RefundRadar · applies RBI/2019-20/67 as code · self-help tool, not legal advice —
    verify details before submitting any complaint.</footer>
</div>
</body>
</html>
"""


def main():
    DOCS.mkdir(exist_ok=True)
    audit, pack = build_demo_data()
    (DOCS / "index.html").write_text(render(audit, pack), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {DOCS / 'index.html'} — demo shows {rupee(audit['total_owed_inr'])} owed")


if __name__ == "__main__":
    main()
