<p align="center"><img src="assets/hero-refundradar.svg" width="100%" alt="RefundRadar"/></p>

![Part of Dhanush Labs](https://img.shields.io/badge/PART_OF-DHANUSH_LABS-6366F1?style=flat-square&labelColor=0A0B0D)
![Status](https://img.shields.io/badge/STATUS-V0.9_BETA-14B8A6?style=flat-square&labelColor=0A0B0D)
![Tests](https://img.shields.io/badge/TESTS-231_PASSING-14B8A6?style=flat-square&labelColor=0A0B0D)
![License](https://img.shields.io/badge/LICENSE-MIT-6366F1?style=flat-square&labelColor=0A0B0D)

### The Payments Auditor Your Bank Hopes You Never Run

**[▶ Try the live demo →](https://dhanu2626.github.io/refundradar/)** — the RefundRadar app itself, running in your browser: try the synthetic statement or your own export. No install, no signup, nothing uploaded.

---

## Problem Statement

> [!IMPORTANT]
> When a digital payment fails in India — money debited, credit never arrives — [RBI circular RBI/2019-20/67](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11693) requires your bank to auto-reverse it within a fixed deadline and pay you ₹100 per day of delay, *suo moto*, without you complaining. In practice, almost nobody checks whether the bank complied. RefundRadar checks.

## Architecture

```
STATEMENT (.xlsx/.csv) ──parse──► RECONCILE debit ↔ reversal
                                        │
                                        ▼
                          APPLY RBI/2019-20/67 AS CODE
                                        │
                                        ▼
                       COMPLAINT PACK (letter + timeline + Ombudsman draft)
```

Everything runs locally — no server, no upload, statements never leave your machine.

## How It Works

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m refundradar serve
```

Open `http://127.0.0.1:8626` → drop a generic CSV or an HDFC export (`.csv`, `.xls`, `.xlsx`, or the Delimited `.txt`), or "Try with a demo statement." Or via CLI: `python -m refundradar audit mystatement.xlsx` (`--password` for SBI-locked files).

## Features

- **Parses real bank exports** — Excel/CSV, including SBI's password-protected files.
- **Reconciles every failed debit against its reversal** — flags late or missing refunds, ignores genuine merchant refunds.
- **Applies the circular as code** — computes exactly what's owed, clause by clause.
- **Generates the complaint pack** — grievance letter with evidence table, 30-day escalation timeline, pre-filled RBI Ombudsman draft.
- **Privacy by construction** — no name, DOB, phone, or login ever requested; `.gitignore` refuses real statement files by design.

## Screenshots

> [!NOTE]
> Add captures of the demo audit flow and a sample complaint pack output here.

## Interactive Demo

**[dhanu2626.github.io/refundradar](https://dhanu2626.github.io/refundradar/)** is the app you run locally, not a copy: the same page, and the same Python code (`refundradar/`) running in your browser on [Pyodide](https://pyodide.org), which the site serves itself. Drop a statement, answer its questions, generate the letter.

- **Nothing is uploaded.** Your file is read inside the page. There is no server behind it, and the page's Content-Security-Policy lets it connect only to its own site, so the browser itself refuses to send anything elsewhere.
- **The first visit downloads about 14 MB** (the Python runtime), cached after that. Audits then run on your device.
- **HDFC reading is synthetically tested**, not yet verified against a real HDFC export, and the page says so beside every HDFC result.
- **Run the demo locally:** `python tools/build_demo_page.py`, then `python -m http.server -d docs 8000` and open `http://localhost:8000` (it needs http, not a `file://` path).

## Engineering Decisions

Every judgment call is written down with reasoning and residual risk in `rules/DECISIONS.md`:

| Decision | Reasoning |
|---|---|
| Deadlines counted in calendar days | The circular defines T as a calendar date |
| NEFT excluded | Falls under a different regime (penal interest at repo + 2%) |
| Ambiguous UPI defaults to the longer deadline | Keeps the claim undisputable |
| Inferred reversals never auto-claimed | User confirms first, even when detectable from amount/timing |
| Payments with no reference are confirmed by their row | The statement prints nothing to confirm by; none is invented, and the letter says "not printed on statement" |

> [!WARNING]
> This is a self-help tool applying published RBI circulars to your own statement. It is **not legal advice** — verify every figure before submitting a complaint.

## Project Structure

```
refundradar/
├── refundradar/           parsing, reconciliation, RBI rule engine, complaint generator
├── rules/DECISIONS.md     every judgment call, written down
├── tests/                 231 tests incl. planted-ground-truth reconciliation exam
└── CONTRIBUTING.md        how to add a bank parser
```

## Tech Stack

Python · pandas (statement parsing) · pytest

## Results

| Statement format | Status |
|---|---|
| SBI Excel/CSV (incl. password-protected; CLI) | ✅ field-tested on a real statement |
| HDFC Excel / Delimited export (web app and CLI) | 🧪 synthetic-tested — awaiting a real-statement field test |
| Generic CSV | ✅ |
| Other banks | 🚧 in progress |
| PDF statements | 🚧 planned |

231 tests passing, including a planted-ground-truth exam the reconciler must pass (find every failure, fall for no traps), plus a live field test on a real SBI statement.

## Future Improvements

More bank formats, PDF statement parsing, per-bank grievance-cell addresses (v1.0 roadmap in `PROJECT.md`), and the RBI Account Aggregator consent-based "connect your bank" flow documented as the v2 ambition in `UX-SPEC.md`.

## Lessons Learned

Data minimization turned out to be a product strategy, not just a constraint — an app that never asks for identity data can't leak it. The canonical schema was built so an Account Aggregator feed would plug in as just another parser, not a rewrite.

## License

MIT © 2026 Dhanush Jangadi

## Contact

Dhanush Jangadi — [GitHub](https://github.com/Dhanu2626) · [LinkedIn](https://www.linkedin.com/in/jangadidhanush)

---
<p align="center"><sub>Part of the <b>Dhanush Labs</b> portfolio · engineered by <a href="https://github.com/Dhanu2626">Dhanush Jangadi</a></sub></p>
