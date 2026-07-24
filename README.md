# RefundRadar

![tests](https://github.com/Dhanu2626/refundradar/actions/workflows/ci.yml/badge.svg)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**The payments auditor your bank hopes you never run.**

▶️ **[Try the live demo](https://dhanu2626.github.io/refundradar/)** — a real audit of a
synthetic statement. No install, no signup, and the demo page cannot receive a file.

When a digital payment fails in India — money debited, credit never arrives — RBI circular
[RBI/2019-20/67 (20 September 2019)](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11693)
requires your bank to auto-reverse it within a fixed deadline (T+1 calendar day for UPI
person-to-person, T+5 for UPI merchant payments and ATMs) and to pay you **₹100 for every
day of delay — *suo moto*, without you even complaining.**

In practice, almost nobody checks whether the bank complied. RefundRadar checks.

## What it does

1. **Parses** your bank statement export — Excel or CSV, including SBI's password-protected files.
2. **Reconciles** every failed debit against its reversal — finds refunds that came late,
   or never came at all, while ignoring genuine merchant refunds.
3. **Applies the RBI circular as code** and computes exactly what your bank owes you,
   clause by clause.
4. **Generates the complaint pack** — grievance letter with an evidence table, a 30-day
   escalation timeline, and a pre-filled RBI Ombudsman draft.

## Privacy: local-first, always

Everything runs on your own machine. No signup, no server, no upload.
Your bank statements never leave your laptop. The repo's `.gitignore` refuses
real statement files by design; only synthetic demo data is ever committed.
When a statement is password-protected, you supply the password at runtime —
it is never stored or logged.

**Data minimisation is deliberate product strategy, not a limitation.** The app
never asks for a name, DOB, phone number, or login — the statement file already
contains every transaction the audit needs, and an app that asks for nothing
can't leak anything. The consent-based "connect your bank" future (RBI's Account
Aggregator rail) is documented as the v2 ambition in [UX-SPEC.md](UX-SPEC.md) —
the canonical schema means an AA feed would plug in as just another parser.

## Run it

**Windows**

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m refundradar serve
```

**macOS / Linux**

```
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m refundradar serve
```

Then open **http://127.0.0.1:8626** and click **"Try with a demo statement"**.

Prefer the terminal?

```
python -m refundradar demo                     # audit the built-in synthetic statement
python -m refundradar audit mystatement.xlsx   # audit your own (--password if locked)
python -m pytest -q                            # run the test suite
```

## Statement formats

| Format | Status |
|---|---|
| SBI Excel/CSV export, including password-protected files | ✅ field-tested on a real statement |
| Generic CSV (`Date, Narration, Ref, Debit, Credit, Balance`) | ✅ |
| Other banks | 🚧 each needs a small parser — see [CONTRIBUTING.md](CONTRIBUTING.md) |
| PDF statements | 🚧 planned |

## How it decides

Financial rules are full of judgment calls, so every one of them is written down with its
reasoning and residual risk in **[rules/DECISIONS.md](rules/DECISIONS.md)** — for example:

- deadlines are counted in calendar days, because the circular defines T as a calendar date
- NEFT is excluded: it falls under a different regime (penal interest at repo + 2%)
- ambiguous UPI payments default to the *longer* deadline, so the claim is undisputable
- a reversal we inferred from amount and timing (SBI issues them under a fresh reference)
  is never claimed automatically — the user confirms it first

## Status

✅ **v0.9 beta** — the full journey works end to end in the browser and the CLI:
parse → reconcile → audit → complaint pack. **69 tests**, including a planted-ground-truth
exam the reconciler must pass (find every failure, fall for no traps), plus a live
field test on a real SBI statement.

Remaining for v1.0: more bank formats, PDF statements, per-bank grievance-cell addresses.
Roadmap in [PROJECT.md](PROJECT.md).

## Disclaimer

RefundRadar is a self-help tool that applies RBI's published circulars to your own
statement. It is not legal advice. Verify every figure against your records before
submitting a complaint.

## License

[MIT](LICENSE) © 2026 Dhanush Jangadi
