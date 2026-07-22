# RefundRadar

![tests](https://github.com/Dhanu2626/refundradar/actions/workflows/ci.yml/badge.svg)

**The payments auditor your bank hopes you never run.**

When a digital payment fails in India — money debited, credit never arrives — RBI circular
[RBI/2019-20/67 (Sept 20, 2019)](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11693)
requires your bank to auto-reverse it within a fixed deadline (T+1 calendar day for UPI
person-to-person, T+5 for UPI merchant payments and ATMs) and to pay you **₹100 for every
day of delay — *suo moto*, without you even complaining.**

In practice, almost nobody checks whether the bank complied. RefundRadar checks.

## What it does

1. **Parses** your exported bank statement (CSV/PDF) into a clean transaction ledger.
2. **Reconciles** every failed debit against its reversal — finds refunds that came late
   or never came at all.
3. **Applies the RBI circular as code** and computes exactly what your bank owes you,
   clause by clause.
4. **Generates the complaint pack** — grievance letter with evidence, escalation timer,
   pre-filled RBI Ombudsman draft.

## Privacy: local-first, always

Everything runs on your own machine. No signup, no server, no upload.
Your bank statements never leave your laptop. The repo's `.gitignore` refuses
real statement files by design; only synthetic demo data is ever committed.

## Status

🚧 Phase 0 — the RBI rulebook encoded as tested code. See [PROJECT.md](PROJECT.md).

## Run the tests

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
```
