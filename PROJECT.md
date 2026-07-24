# PROJECT.md — RefundRadar operating file

Read this first every session ("start day" ritual). Full plan:
`..\REFUNDRADAR-PLAN.md` (CareerForge root).

## Current phase: 1 — Statement ingestion (Phase 0 ✅ complete 2026-07-22)

| Slice | Status |
|---|---|
| 0.1 Repo scaffold, README, ledgers, .gitignore | ✅ 2026-07-22 |
| 0.2 Read RBI/2019-20/67, encode annex as `rules/rbi_tat.yaml` | ✅ 2026-07-22 |
| 0.3 Rules engine (`refundradar/rules_engine.py`) + unit tests | ✅ 2026-07-22 |
| 0.4 Edge cases researched → `rules/DECISIONS.md` (D1 calendar days, D2 NEFT deferred, D3 PPI off-us inherits rail, D4 floor-not-ceiling) | ✅ 2026-07-22 |
| 1.1 Canonical transaction schema (`refundradar/model.py`) + channel-detection heuristics from narration text | ✅ 2026-07-22 |
| 1.2 Synthetic statement generator (`refundradar/synth.py` → `samples/`) with 4 planted failures + 1 false-positive trap, answer key from the rules engine | ✅ 2026-07-23 |
| 1.3 Parser: generic CSV → canonical schema (`refundradar/parser.py`) | ✅ 2026-07-23 |
| 2. Reconciliation engine (`refundradar/reconcile.py`) — passes the planted exam: finds all incidents, dodges the merchant-refund trap | ✅ 2026-07-23 |
| 3. Audit aggregation (`refundradar/audit.py`) — totals, per-incident rulings | ✅ 2026-07-23 |
| 4. Complaint pack generator (`refundradar/complaint.py`) — bank letter + evidence table + ombudsman draft | ✅ 2026-07-23 |
| 5. Web app (`refundradar/webapp.py` + `static/index.html`) — drop zone, demo mode, audit screen, confirm flow, complaint download; verified live in browser | ✅ 2026-07-23 |
| CLI (`python -m refundradar serve|audit|demo`) | ✅ 2026-07-23 |

## Roadmap to v1.0 — council order (4-agent review, 2026-07-24)

1. **Real-statement field test** ✅ 2026-07-24 — SBI parser (encrypted-OLE2
   sniffing, "Details" column, WDL/DEP TFR narrations); first real audit = Rs.0
   owed (verified honest); discovered SBI reverses under a fresh reference →
   amount+timing fallback matching (D9). 106 real txns parsed.
2. **Honesty layer** — D8 time-barred flag + self-help disclaimer ✅ 2026-07-24
3. **Public demo page** ✅ 2026-07-24 — static synthetic-only page (no upload
   possible), built by tools/build_demo_page.py from the real engine output,
   live at https://dhanu2626.github.io/refundradar/ (GitHub Pages, main /docs)
4. **Statement-download helper** — per-bank export guide (UX-SPEC screen 1) ⬅ NEXT

Deferred post-v1.0: Hindi/Telugu UI, packaged .exe, SMS parsing, PDF statements,
per-bank grievance addresses, mobile.

## Next phases (see plan for detail)

- **Phase 1** — statement ingestion: canonical txn schema, CSV parsers (SBI/HDFC/ICICI/Kotak),
  PDF via pdfplumber, synthetic statement generator
- **Phase 2** — reconciliation engine (UTR/RRN matching + heuristics) + accuracy harness
- **Phase 3** — audit report ("your bank owes you ₹X")
- **Phase 4** — complaint pack generator + escalation deadline tracker
- **Phase 5** — local web UI (FastAPI) + demo mode
- **Phase 6** — ship: docs, demo video, LinkedIn, community bank-format PRs

## Rituals

- **start day** → read this file + last FIELD-NOTES entry → agree one slice → build it
- **close day** → commit → 3 insights to `ledger/FIELD-NOTES.md` → interview line to
  `ledger/INTERVIEW-AMMO.md` → new terms to `ledger/GLOSSARY.md`
- **weekly** → /code-review + accuracy harness + LinkedIn progress post
