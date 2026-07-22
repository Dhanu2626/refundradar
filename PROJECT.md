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
| 1.3 First real parser: one bank's CSV export → canonical schema | ⬜ |

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
