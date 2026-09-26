"""Generate the public demo page (docs/index.html) for GitHub Pages.

The page is the web app's own page (refundradar/static/index.html): the same
markup, styles and findings renderer, so the live demo looks and reads exactly
like the app. The app marks the few blocks that must differ with demo-swap
comments, and they are replaced here by versions that take no file. The page
has no file input, no form and no network call: the one audit it can show is
the app's own answer for the synthetic demo statement, frozen at build time,
so the "your statement never leaves your computer" promise cannot be violated
here.

Re-run after any engine or web app change:  python tools/build_demo_page.py
(tests/test_demo_page.py fails while docs/index.html is out of date).
"""

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from refundradar.webapp import (INDEX, AuditRequest, ComplaintRequest, audit_endpoint,
                                complaint_endpoint, demo)

DOCS = ROOT / "docs"
AS_OF = date(2026, 7, 24)  # frozen so the demo numbers are stable
SAMPLE = {"name": "A. Sample Customer", "account_last4": "2626",
          "contact": "sample@example.com"}
FILE_NAME = "demo_statement.csv (synthetic)"  # what the app calls its demo statement

REPO_URL = "https://github.com/Dhanu2626/refundradar"
RUN_IT = REPO_URL + "#how-it-works"

SWAP = re.compile(r"<!-- demo-swap:(\w+) -->.*?<!-- /demo-swap:\1 -->", re.S)
# what would let the page take a file or reach the network
UPLOAD_SURFACE = ("<input", "<form", "fetch(", "xmlhttprequest", "websocket", "sendbeacon",
                  "filereader", "<script src", "<iframe")


def build_demo_data():
    """The app's answers for its own demo statement, as of AS_OF: the audit
    response and the complaint pack for a sample customer."""
    d = demo()
    req = {"csv": d["csv"], "confirmed": d["suggested_confirmed"], "as_of": AS_OF.isoformat()}
    data = audit_endpoint(AuditRequest(**req))
    pack = complaint_endpoint(ComplaintRequest(**req, **SAMPLE))
    # The page can't audit again, so it must never ask a question.
    if data["unmatched"] or any(i["action"] != "none" for i in data["audit"]["incidents"]):
        raise SystemExit("The demo statement now asks a question the static page can't "
                         "answer. Change the demo statement, or give the page a way to answer.")
    # It shows channel names, never codes, and has no search box: it carries
    # neither the codes nor the statement's list of payments.
    for i in data["audit"]["incidents"]:
        if not i["channel_name"]:
            raise SystemExit(f"No channel name for {i['ref']}: the demo would show a code.")
        del i["channel"]
    data["candidates"] = []
    return data, pack


def rupees(n) -> str:
    """Whole rupees in Indian digit grouping, as the app shows them (₹1,00,000)."""
    digits = str(int(n))
    head, groups = digits[:-3], [digits[-3:]]
    while len(head) > 2:
        head, groups = head[:-2], [head[-2:]] + groups
    return "₹" + ",".join(([head] if head else []) + groups)


def icon(name: str) -> str:
    return f'<svg class="ic" aria-hidden="true"><use href="#i-{name}"/></svg>'


def demo_parts(data: dict, pack: str, confirmed: list) -> dict:
    """The page's own version of each block the app marks with demo-swap."""
    a = data["audit"]
    as_of = date.fromisoformat(a["as_of"]).strftime("%d %b %Y")
    shown = any(i["ref"] in confirmed for i in a["incidents"])
    blob = json.dumps({"file_name": FILE_NAME, "response": data, "pack": pack,
                       "confirmed": confirmed}, ensure_ascii=False)
    sample = {k: html.escape(v) for k, v in SAMPLE.items()}
    return {
        "title": """<title>RefundRadar — the payments auditor your bank hopes you never run</title>
<meta name="description" content="RBI requires your bank to pay you Rs.100/day for late refunds on failed payments, automatically. Almost nobody checks. RefundRadar does.">""",
        "privacy": f"""<section class="privacy" aria-labelledby="privacy-h">
      <h2 id="privacy-h">{icon("shield")}Live demo</h2>
      <ul>
        <li>{icon("check")}A synthetic statement. No real account.</li>
        <li>{icon("check")}This page can't take a file, and sends nothing anywhere.</li>
        <li>{icon("check")}The app itself runs on your own computer.</li>
      </ul>
    </section>""",
        "doorway": f"""<div class="drop demo">
        <div class="up">{icon("play")}</div>
        <strong>Run a real audit on a sample statement</strong>
        <p class="or">It finds the {rupees(a["total_owed_inr"])} a bank owes this made-up customer, and shows its work.</p>
        <div class="formats"><span class="chip">Synthetic data</span>
          <span class="chip">{a["statement_lines"]} transactions</span><span class="chip">As of {as_of}</span></div>
        <p class="note">This page can't take a file: it has no upload, and nothing you do here
          leaves your browser. To audit your own statement,
          <a href="{RUN_IT}">run RefundRadar on your computer</a>.</p>
        <button type="button" class="primary choose" id="demo-btn">{icon("play")}Run the demo audit</button>
      </div>
      <noscript><p class="error" style="display:block">This demo needs JavaScript to show the audit.</p></noscript>
      <div class="status" id="status" role="status" aria-live="polite"></div>""",
        "new": f'<a class="button ghost" href="{RUN_IT}">Audit your own statement</a>',
        "confirm": """<p class="hint">The statement alone can't prove a failure that was never
          reversed &mdash; a failed payment looks identical to a successful one.
          In the app, you search the payment you remember and confirm it.</p>"""
        + ("""
        <p class="verify">This demo confirmed one for you: <b id="demo-confirmed"></b>.
          It is the &ldquo;Still missing&rdquo; finding above.</p>""" if shown else ""),
        "fields": f"""<div class="fields">
          <div class="field"><span class="ro-label">Name as on the account</span><div class="ro">{sample["name"]}</div></div>
          <div class="field"><span class="ro-label">Account last 4 digits</span><div class="ro">{sample["account_last4"]}</div></div>
          <div class="field"><span class="ro-label">Email or phone for the reply</span><div class="ro">{sample["contact"]}</div></div>
        </div>
        <p class="hint">The demo fills these in for a sample customer. In the app, you type
          your own, and they go only into the letter.</p>""",
        "footer": "<span>RefundRadar &mdash; applies RBI/2019-20/67 as code. This demo reads a "
                  "synthetic statement; the app runs 100% on your computer.</span>",
        # "<" escaped: the statement's text can never close the script element
        "io": ('<script type="application/json" id="demo-data">'
               + blob.replace("<", "\\u003c") + "</script>\n" + DEMO_SCRIPT),
    }


DEMO_SCRIPT = """<script>
// The public demo, built by tools/build_demo_page.py: what the app answers for its
// demo statement, frozen into this page. It has no file input, no form and no
// network call, so it can never receive a statement.
const DEMO = JSON.parse($("demo-data").textContent);

$("demo-btn").addEventListener("click", () => {
  showError("");
  state.fileName = DEMO.file_name;
  render(DEMO.response);
  const note = $("demo-confirmed");
  if (note) note.textContent = DEMO.response.audit.incidents
    .filter((i) => DEMO.confirmed.includes(i.ref))
    .map((i) => `${i.channel_name} · ${inr(i.amount)} · ${day(i.date)}`).join("; ");
  setStatus("Audit complete.");
});

$("pack-btn").addEventListener("click", () => { showError(""); showPack(DEMO.pack); });
$("reset-btn").addEventListener("click", () => location.reload());

// a file dropped here is never read: say so, rather than let the browser open it
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => {
  e.preventDefault();
  showError("This live demo can't take a file, and it didn't read that one. " +
            "To audit your own statement, run RefundRadar on your computer.");
  window.scrollTo(0, 0);
});
</script>"""

BANNER = f"""<div class="demo-bar"><span class="pill">Live demo</span><span>Synthetic statement &middot;
  this page can't take a file &middot; <a href="{REPO_URL}">Get RefundRadar on GitHub</a></span></div>
"""

DEMO_CSS = """
  /* the public demo's few rules of its own; everything else is the app's */
  .demo-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: center;
              gap: 4px 10px; min-height: 40px; padding: 8px 16px; border-bottom: 1px solid var(--line);
              background: #0d1b1b; color: var(--ink-2); font-size: 13px; text-align: center; }
  .demo-bar .pill { padding: 2px 9px; border-radius: 999px; background: var(--brand);
                    color: var(--accent-ink); font-size: 11.5px; font-weight: 800;
                    letter-spacing: .06em; text-transform: uppercase; }
  .demo-bar a, .drop.demo a { color: var(--accent); font-weight: 600; text-underline-offset: 3px; }
  .shell { min-height: calc(100vh - 40px); }
  @media (min-width: 1024px) { .side { height: calc(100vh - 40px); } }
  .drop.demo, .drop.demo:hover { cursor: default; border-style: solid;
                                 border-color: rgba(45, 212, 191, .3); }
  a.button { display: inline-flex; align-items: center; justify-content: center; gap: 8px;
             min-height: 44px; padding: 0 18px; border-radius: 12px; border: 1px solid var(--line-2);
             color: var(--ink); font-size: 14.5px; font-weight: 600; text-decoration: none;
             transition: background-color .15s, border-color .15s; }
  a.button:hover { background: var(--surface-2); border-color: #414856; }
  .ro-label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600;
              color: var(--ink-2); }
  .ro { min-height: 44px; padding: 10px 12px; border-radius: 10px; border: 1px dashed var(--line-2);
        background: var(--bg); color: var(--ink-2); overflow-wrap: anywhere; }
"""


def render(data: dict, pack: str) -> str:
    """The app's page with its demo-swap blocks replaced: the public demo."""
    page = INDEX.read_text(encoding="utf-8")
    parts = demo_parts(data, pack, demo()["suggested_confirmed"])
    marked = SWAP.findall(page)
    if sorted(marked) != sorted(parts):
        raise SystemExit(f"{INDEX.name} marks the demo-swap blocks {sorted(marked)}; "
                         f"this build replaces {sorted(parts)}. Make them agree.")
    page = SWAP.sub(lambda m: parts[m.group(1)], page)
    for anchor, added in (("</head>", f"<style>{DEMO_CSS}</style>\n</head>"),
                          ('<div class="shell">', BANNER + '<div class="shell">')):
        if page.count(anchor) != 1:
            raise SystemExit(f"{INDEX.name} no longer has exactly one {anchor!r}.")
        page = page.replace(anchor, added)
    found = [s for s in UPLOAD_SURFACE if s in page.lower()]
    if found:
        raise SystemExit(f"The demo page would contain {found}: it must not take a file.")
    return page


def main():
    DOCS.mkdir(exist_ok=True)
    data, pack = build_demo_data()
    (DOCS / "index.html").write_text(render(data, pack), encoding="utf-8", newline="\n")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {DOCS / 'index.html'}: the app's page, showing "
          f"{rupees(data['audit']['total_owed_inr'])} owed as of {AS_OF}")


if __name__ == "__main__":
    main()
