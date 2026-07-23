# Field Notes — daily insights from building RefundRadar

## Day 1 — 2026-07-22 · Phase 0: the rulebook becomes code

🏦 **Payments/RegTech insight:** RBI's TAT circular deliberately gives person-to-person
transfers (UPI P2P, IMPS) a T+1 deadline but merchant payments (UPI P2M, PoS, e-com)
T+5. Why? P2P failure is purely between two banks — fast to verify. Merchant failure
involves a third party's confirmation (did the charge-slip generate? did the acquirer
confirm?), so the chain is longer. Deadlines in regulation mirror the *settlement chain
length* — once you see that, the whole annex table stops being arbitrary.

🔧 **Engineering insight:** we encoded the regulation as *data* (YAML) and kept the
engine generic, instead of hard-coding `if channel == "upi_p2p"`. When RBI amends the
circular — or we add NEFT's separate penal-interest regime — we edit a data file, not
logic. "Rules as data, engine as code" is the core RegTech pattern.

🎯 **Interview line:** "I read RBI's TAT harmonisation circular at clause level and
encoded its annex as a tested rules engine — every deadline and the ₹100/day suo-moto
compensation — so the regulation itself became executable, verifiable code."

**Open thread for slice 0.4:** does "T+1 day" mean calendar day in ALL bank
interpretations? Circular says T = calendar date, but ombudsman awards vary on
weekend handling. Research + record in rules/DECISIONS.md.

## Day 2 — 2026-07-22 · Phase 0 complete: the edge cases

🏦 **Payments/RegTech insight:** one "failed payment" can fall under three different
compensation regimes: flat ₹100/day (UPI/IMPS/cards, the 2019 TAT circular),
penal interest at repo+2% (NEFT, a 2010 circular), or the underlying rail's rule
(wallet off-us — the circular literally says the transaction "rides on" UPI/card/IMPS
and that system's rule applies). Regulation isn't one rulebook; it's layers, and
knowing WHICH layer governs a transaction is half the compliance job.

🔧 **Engineering insight:** we wrote a decision log (rules/DECISIONS.md) instead of
burying interpretations in code comments. Every ambiguous reading — calendar vs
working days, NEFT deferral — is recorded with reasoning and remaining risk. In
regulated software, "why we compute it this way" is as much a deliverable as the
computation; auditors and ombudsmen ask for exactly this.

🎯 **Interview line:** "When the regulation was ambiguous — calendar versus working
days — I didn't guess silently; I documented the interpretation, the clause supporting
it, and the residual risk in a decision log, the way a compliance function would."

**Next session (Phase 1):** canonical transaction schema + channel detection from
narration strings — the first step of teaching the tool to read real statements.

## Day 3 — 2026-07-22 · Slice 1.1: the canonical schema

🏦 **Payments/RegTech insight:** a bank statement's narration line is a dialect, not
a standard — `UPI/DR/519912345678/...`, `ATW-...`, `ACH-DR-...` — and the SAME
transaction type is written differently by every bank. Worse, the narration doesn't
tell you the counterparty type: whether a UPI payment went to a person (T+1 refund
deadline) or a merchant (T+5) must be inferred. We infer conservatively (D5): when
unsure, assume the deadline that favors the bank, so every rupee we claim survives
scrutiny. Under-claiming slightly beats over-claiming and being dismissed.

🔧 **Engineering insight:** two traps caught today. (1) "PAYTM" contains the letters
"ATM" — naive substring matching would classify a lunch payment as an ATM withdrawal;
regex word boundaries (\bATM\b) are load-bearing. (2) Money must be Decimal, never
float: 0.1 + 0.2 != 0.3 in binary floating point, and a compensation auditor that's
off by a paisa loses all credibility. `Decimal(str(x))` at the door, everywhere.

🎯 **Interview line:** "I designed a canonical schema so N bank formats × 1 auditor
stays N parsers, not N×M format-aware components — every parser normalizes into one
Transaction model and everything downstream is bank-agnostic."

**Next session:** slice 1.2 — the synthetic statement generator with planted
failures, our ground truth for measuring reconciliation accuracy in Phase 2.

## Day 4 — 2026-07-23 · Slice 1.2: the statement factory + product stance

🏦 **Payments/RegTech insight:** a credit with the same reference number as a debit
is NOT always a failed-transaction reversal — a genuine merchant refund (returned
order) looks structurally identical. The signal lives in narration language ("REV
OF FAILED TXN" vs "REFUND ORDER RETURN") and timing. Our synthetic statement plants
exactly this trap so Phase 2's reconciler is forced to learn the difference —
wrongly claiming ₹500 on a Myntra return would sink a real complaint's credibility.
Also banked today: the v1/v2 data stance — data minimisation now, Account
Aggregator (consent-rail) as the documented regulated-entity ambition.

🔧 **Engineering insight:** two patterns. (1) Deterministic randomness — the
generator takes a seed, so "random-looking" data is perfectly reproducible and
therefore testable; flaky test data is worse than no test data. (2) Single source
of truth — the answer key's expected compensation is computed BY the rules engine
itself, so the grader and the graded can never drift apart silently.

🎯 **Interview line:** "Before building the detector, I built the exam it has to
pass: synthetic statements with planted failures and one false-positive trap,
graded as precision and recall — because 'it seems to work' is not a metric."

**Next session:** slice 1.3 — the first real parser: read the generic CSV format
into canonical Transactions, and the engine reads its first full statement.

## Day 5 — 2026-07-23 · The full build: parser → detective → audit → letter → app

🏦 **Payments/RegTech insight:** the deepest finding of the build — a failed payment
that was never reversed is INVISIBLE in a statement; it looks exactly like a
successful payment. Only reversed failures leave a two-row trace. So the audit
architecture must split into "what the statement proves" (automated) and "what only
the customer knows" (confirmed via UI, D6) — and a legal letter may contain only
the union of proof and confirmation, never guesses. One fabricated incident would
poison the credibility of every real one.

🔧 **Engineering insight:** the server holds NO state — the browser keeps the
statement text and re-sends it with each request. That single choice makes the
privacy promise structural (nothing to store = nothing to leak), makes the API
trivially testable, and eliminated a whole class of session bugs. Also: the
reconciler shipped only after passing a pre-built exam (planted ground truth,
100% precision/recall including the trap) — test-first pays off most at the
riskiest layer.

🎯 **Interview line:** "My reconciler couldn't ship until it passed an exam I built
first: synthetic statements with planted failures and a merchant-refund trap.
It scores 100% precision and recall on ground truth — and the never-reversed case
taught me that some fraud/ops signals structurally cannot come from data alone;
you have to design the human confirmation into the product."

**Next:** real bank CSV formats (HDFC/SBI/ICICI), PDF statements, field test on
family statements. The engine is done; v1.0 is about meeting real data.

## Day 6 — 2026-07-24 · Council verdict + the honesty layer (D8)

🏦 **Payments/RegTech insight:** a claim's age changes its nature. Under RB-IOS
2021 the ombudsman window runs from the bank's reply to your complaint — not from
the transaction — so old incidents aren't legally dead, but banks contest stale
claims and one rebuffed line item taints the whole letter. So RefundRadar now
splits the audit into "the number nobody can argue with" (headline, < 1 year) and
"informational older incidents" (listed, flagged, out of the demand). Compliance
thinking is largely the art of deciding what NOT to claim.

🔧 **Engineering insight:** the 4-agent council format surfaced a synthesis no
single viewpoint had: a hosted demo AND the local-only privacy story can coexist
if the public page is structurally incapable of receiving uploads (synthetic-only
demo build). Constraints don't always trade off; sometimes an architecture
dissolves the conflict.

🎯 **Interview line:** "My audit flags claims older than a year and keeps them out
of the headline and the letter — because under RB-IOS 2021 the window runs from
the bank's reply, banks contest stale claims, and the headline must be the amount
nobody can argue with."

**Next:** the field test — first real statement ever. Parser for Dhanush's own
bank format; every narration surprise becomes a fix and a field note.
