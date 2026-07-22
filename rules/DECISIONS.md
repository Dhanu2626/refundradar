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
