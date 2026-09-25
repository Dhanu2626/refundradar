# Contributing

The most useful thing you can add is **your bank's statement format**.

RefundRadar reads every bank into one canonical `Transaction` shape, so supporting a new
bank means writing one small reader — nothing downstream changes.

## Never commit a real statement

`.gitignore` blocks `statements/`, `*.xlsx`, `*.csv`, and `*.pdf` on purpose. When you add
a bank, build a **synthetic sample** that mimics the layout (fake names, fake amounts,
fake references) and test against that. Real data stays on your machine, always.

## Adding a bank

1. Export a statement from your bank and open it locally — note the header row, the exact
   column names, the date format, and how the narration is worded.
2. Add a mapper in [`refundradar/parser.py`](refundradar/parser.py) alongside
   `parse_sbi_rows` and `parse_hdfc_rows`, and route to it from `_parse_bank_rows` on a
   header signature only your bank's layout carries. Map columns **by header name, not
   position** — banks reshuffle layouts.
3. Add tests in `tests/` using synthetic rows in that bank's shape. Cover: the header hiding
   below preamble rows, both text and serial dates, comma-formatted amounts, and any
   reversal wording the bank uses.
4. Check whether the bank ties a reversal to the original payment by reference. Some (SBI)
   issue reversals under a **fresh** reference — if so, the amount+timing fallback in
   [`refundradar/reconcile.py`](refundradar/reconcile.py) is what catches it.
5. Run `python -m pytest -q` and open a pull request.

## Ground rules

- Anything ambiguous in the regulation gets recorded in [`rules/DECISIONS.md`](rules/DECISIONS.md)
  with the reasoning and the residual risk — not buried in a code comment.
- When unsure, choose the reading that produces the **smaller, undisputable** claim.
  An inflated number that a bank can rebut damages every other line in the letter.
- Never let an inferred conclusion enter a complaint letter without user confirmation.
