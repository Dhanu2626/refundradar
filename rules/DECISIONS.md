# Decision log — how RefundRadar interprets the rules

Every judgment call in the compensation math, written down with reasoning.
Format: what we decided, why, and what risk remains.

---

## D1 — Deadlines are computed in CALENDAR days (2026-07-22)

**Decision:** `T+n` means n calendar days after the transaction date. No weekend or
holiday adjustment.

**Why:** The circular explicitly defines "T is the day of transaction and refers to the
calendar date," and is otherwise silent on weekends/holidays. The systems it governs
(UPI, IMPS, ATM) run 24x7 — auto-reversal is machine work, not clerk work.

**Risk:** A bank could argue "working days" in a dispute. Our complaint letters cite the
circular's own calendar-date definition, which is the stronger reading. If ombudsman
practice ever contradicts this, add a `working_days` mode behind a config flag.

## D2 — NEFT/RTGS are OUT of scope for the ₹100/day engine; separate regime, deferred (2026-07-22)

**Decision:** NEFT and RTGS are not in `rbi_tat.yaml` and the engine refuses them
(unknown channel). Support comes later as a second compensation regime.

**Why:** Verified the TAT circular never mentions NEFT/RTGS. NEFT has its own rule
(RBI circular DPSS (CO) EPPD No. 477/04.03.01/2010-11, Sept 1, 2010): if not credited
or returned within 2 hours of batch settlement, the bank owes **penal interest at RBI
LAF Repo Rate + 2%** for the delay period — also suo moto. That's interest-on-amount
math, not flat ₹100/day, and needs a repo-rate history table to compute historically.

**Plan:** implement as `regime: penal_interest` after Phase 2, when the parser tells us
how often NEFT failures actually appear in real statements.

## D3 — PPI off-us transactions map to their underlying rail (2026-07-22)

**Decision:** No separate `ppi_off_us` channel. The reconciler (Phase 2) will classify
a wallet transaction by the rail it rode on (UPI/card/IMPS) and apply that rail's rule.

**Why:** The circular says it directly: for PPI off-us, "the transaction will ride on
UPI, card network, IMPS, etc. … The TAT and compensation rule of respective system
shall apply." Encoding a duplicate channel would just drift from the underlying rules.

## D4 — The circular is a floor, not a ceiling (2026-07-22)

**Note:** The circular doesn't discuss banks' own compensation policies. Banks may pay
more under their board-approved customer compensation policies; they cannot pay less
than the framework. Audit reports state compensation as "minimum owed under
RBI/2019-20/67" — deliberately conservative, harder to dispute.

## D5 — Ambiguous UPI transactions default to P2M, the longer deadline (2026-07-22)

**Decision:** `detect_channel()` classifies a UPI narration as `upi_p2p` (T+1) only on
clear person-side evidence — a phone-number VPA (`9876543210@...`) or a literal P2P
tag. Merchant markers (QR, gateway VPAs like Razorpay/BharatPe/PayU) and everything
ambiguous become `upi_p2m` (T+5).

**Why:** Statement narrations don't label the counterparty type, and guessing P2P
inflates the claim (shorter deadline → more days late → more compensation). Per D4 we
compute the minimum defensible amount: when unsure, assume the deadline that favors
the bank. A disputed ₹500 claim is worth less than an undisputable ₹300 one.

**Risk:** Some genuine P2P transfers (name-based VPAs like `ramesh@okhdfc`) get the
T+5 deadline and under-claim by up to 4 days × ₹100. Acceptable; revisit if Phase 2
reconciliation finds counterparty signals that raise confidence.

## D6 — Never-reversed failures require user confirmation (2026-07-23)

**Decision:** the reconciler never flags a debit as "failed, never refunded" on its
own. A failed payment that was never reversed is statistically identical, on the
statement, to a successful payment. Claiming one without evidence would be a guess
dressed as an audit. The UI therefore asks the user to search and confirm the
payment they know failed; only confirmed refs enter the claim.

**Why:** every claim in the complaint letter must survive the bank's scrutiny. One
fabricated incident poisons the credibility of all the real ones.

## D9 — Amount+timing fallback for banks that reverse under a fresh reference (2026-07-24)

**Decision:** after exact-reference matching, a second pass links a reversal-worded
credit (e.g. SBI's `UPI/REF`) to the closest-in-time unclaimed debit of the same
amount within 10 days. If the inferred pairing is on time, record it as such (Rs.0
at stake); if it looks late, downgrade to `needs_confirmation` — never an automatic
claim.

**Why:** field test on a real SBI statement (2026-07-24) revealed SBI issues
reversal credits with a NEW reference number, not the original payment's. Pure
reference-matching was therefore blind to every SBI failure. The fallback restores
detection, but since an amount+time link is inferred rather than proven, an inferred
LATE match must be user-confirmed before it can enter a claim — same honesty rule as
D6. An inferred on-time match is harmless (nothing is claimed), so it needs no
confirmation.

**Risk:** two same-amount debits near one reversal are genuinely ambiguous (seen in
the field data: a same-day decoy beside an 8-day-old payment). Picking the closest
biases toward the on-time reading, i.e. toward under-claiming — the conservative,
defensible direction (D4).

## D8 — Incidents older than one year leave the headline and the letter (2026-07-24)

**Decision:** claims where the transaction is more than 365 days old (relative to the
audit date) are flagged `time_barred`, excluded from the headline total and from the
letter's demand table, and listed separately as informational.

**Why:** under RB-IOS 2021 the ombudsman window technically runs from the bank's
reply to a complaint, not from the transaction — so old incidents are not strictly
dead. But banks contest stale claims, record-retention gets invoked, and one
successfully rebuffed line item damages the credibility of the whole letter. Same
principle as D4/D5: the headline number must be the amount nobody can argue with.

**Risk:** we under-claim for users with genuinely recoverable older incidents. The
letter still lists them informationally, so the user can pursue them deliberately.

## D7 — v1 UI is a single vanilla-JS page, not React (2026-07-23)

**Decision:** the web app is one HTML file served by FastAPI; the browser holds the
statement text and re-sends it per request, so the server is stateless and stores
nothing (privacy by architecture).

**Why:** no build step, no node toolchain, nothing to break — the whole UI is
readable in one sitting, which fits both the trust story and a solo maintainer.
React remains the right call if/when the UI outgrows one screen.

## D10 — HDFC is parsed strictly until a real export confirms its layout (2026-09-25)

**Decision:** HDFC's Excel and Delimited exports are read from their publicly known
layout, and strictly. Inside the transaction table the only rows passed over are
blank rows, asterisk separators, a repeated header, and dated rows that move no money
and hold nothing else but a nearby value date. Any other row stops the audit, and the
error names the row, the column and the cell: a date that isn't dd/mm/yy (a time of
day after it is fine), an amount or Closing Balance that isn't a plain number, both
amount columns filled, a stray value where no amount is. The parsed rows must
reproduce HDFC's own Closing Balance column, and nothing but totals may follow the
STATEMENT SUMMARY: a second header or a dated row with an amount there is refused.

**Why:** no real HDFC statement has been through the code. A lenient parser fails
silently: a refund row it can't read disappears and the audit still prints a
confident total. Adversarial probes (2026-09-25) found twelve such paths, from a
"450.00 Cr" amount to rows pasted below the summary. Stopping turns each wrong
assumption into a visible, reportable error instead of a wrong number.

**Evidence status:**
- *Confirmed against real HDFC data:* nothing yet.
- *Inferred from HDFC's published layouts, unverified:* the column names of both
  exports; dd/mm/yy dates; asterisk separators and the STATEMENT SUMMARY block; UPI
  narrations shaped `UPI-<name>-<VPA>-<IFSC>-<RRN>-<note>`; the Chq./Ref.No. column
  holding the RRN left-padded with zeros, one reference per transaction; Closing
  Balance as a plain running balance in printed order (oldest first unless the
  dates say otherwise).
- *Unknown, stood in for by the synthetic sample:* how HDFC words a failed-payment
  reversal; whether the reversal repeats the original RRN, and where (narration, ref
  column, both, neither); whether the .xls download is genuine BIFF or an HTML table;
  the Delimited download's file extension (tests assume .txt; the web app accepts
  .txt and .csv, and reads the content whatever the name);
  whether long narrations wrap onto continuation rows.

**Risk:** the first real HDFC statement may stop on a row shape the parser has never
seen, and every inferred rule above is a candidate. That is the intended failure; the
fix belongs in `parse_hdfc_rows` with a synthetic test in that shape. A totals row
that mimics a transaction (a first cell that reads as a date, one amount, and a
balance that happens to add up) would still be read; the STATEMENT SUMMARY label and
the labels row stop that in the layout we know. If the ref column repeats across
unrelated rows, reference matching loses its proof value there (D12 then asks).

## D11 — A verdict needs wording that points one way (2026-09-25)

**Decision:** a credit counts as a merchant refund only when it says REFUND or
CASHBACK and nothing about failure, and as a reversal only when it says REVERSAL,
FAILED, NOT DISPENSED, UPI/REF, … and nothing about refunds or returns.
"RETURNED TO SENDER" is a reversal phrase in its own right. Everything else, meaning
both kinds of wording ("REFUND OF FAILED TXN"), a bare RETURN, or neither, is
ambiguous: a same-reference match on it becomes `needs_confirmation`, and the user's
"Yes, it failed" turns it into a reversal.

**Why:** refund words used to win outright, so "REFUND OF FAILED TXN", a bank
describing a failed payment coming back, was excluded as a returned order, and the
listed reversal phrase "RETURNED TO SENDER" could never fire because it contains
RETURN. A bare RETURN is genuinely two-faced: a returned order, or a transfer
returned unpaid. Neither reading is safe to assume: excluding hides compensation
owed, claiming risks putting a merchant refund in the letter.

**Risk:** more questions for the user. SBI's reversal marker "UPI/REF" also appears
inside "UPI/REFUND", so a same-reference credit worded that way now asks instead of
being excluded. A bare-RETURN credit under a fresh reference is not asked about at
all (too weak to link without a reference); it stays an explicit limitation.

## D12 — Claim only what the statement proves; ask about the rest (2026-09-25)

**Decision:**
1. A credit settles one debit, the closest earlier one it fits; an exact copy of a
   refund row counts as the same refund.
2. A reference proves a link only if no other payment on the statement carries it. A
   late reversal on a shared reference needs confirmation, and a confirmed payment
   whose reference is shared is not claimed at all, because RefundRadar can't tell
   which row the user meant.
3. For a payment the user confirmed failed, with no same-reference credit, every
   unexplained credit of the same amount on or after it is a candidate, whatever its
   wording. Exactly one, reversal-worded and wanted by no other confirmed payment, is
   its refund: claimed on time or late against that date, at any distance. No
   candidate at all means never refunded. Anything else is a question listing the
   candidates' dates.
4. A reversal beyond D9's 10-day window with exactly one payment it could belong to
   is asked about instead of dropped; with several, the statement can't say which.

**Why:** adversarial probes (2026-09-25) found wrong claims in the original matching
and then in the first fixes. The original matching gave one reversal to two copies
of a payment, gave a reused mandate reference's reversal to the wrong instalment,
and called a payment refunded under a fresh reference (SBI's normal behaviour, D9)
"never refunded": Rs.7,800 where at most Rs.100 was owed. The first fixes still
fabricated a "never refunded" claim for a confirmed duplicate row (Rs.8,200 claimed,
Rs.800 owed), claimed never-refunded for a refund worded like an ordinary transfer,
and let two confirmed payments swap each other's refunds. Across 20 adversarial
scenarios, claims above what is owed went 7 → 3 → 0.

**Risk:** every rule errs toward asking or under-claiming (D4), so some owed money
waits on the user. Two questions have no answer in the UI yet: "Yes, it failed" can't
say which of several candidate credits was the refund, or which of several rows
sharing a reference the user meant. Those incidents stay unclaimed until the user
checks by hand; a pairing confirmation is future work. A claim still rests on the
user's own "it failed": confirming a payment that went through is outside what a
statement can catch (D6).

## D13 — A refund the user matches by hand is evidence, bounded by that credit (2026-09-25)

**Decision:** where the statement can't settle a pairing, the web app shows the
candidates and lets the user pick one. That covers a reversal with several possible
payments, a confirmed failure with several candidate credits, and a RETURN under a new
reference. The pick reaches the reconciler as `confirmed_refunds` (payment, refund).
It counts only if both rows are on the statement, the amounts match, the refund is on
or after the payment, and neither row is picked twice. The payment is then ruled on
time or late against that credit's date. Without a pick nothing is claimed ("Unable
to conclusively match"), and the automatic passes behave exactly as before.

**Why:** D12 left these as questions the UI could not answer: "Yes, it failed"
confirms a reference, not which credit refunded which payment. The account holder is
the only honest source for that link, the same evidence D6 already relies on for
failures.

**Risk:** a wrong pick misdates the claim. Because the claim stops at the chosen
credit's date, a wrong pick under-claims when the payment was really never refunded.
It overstates only if the user picks a refund for a payment that did not fail, which
is outside what a statement can catch (as in D6). The UI offers only candidates the
reconciler computed; the API re-checks the structure but not the candidate list, so a
hand-built request is trusted like any confirmation.
