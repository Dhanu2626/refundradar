# Interview Ammo — STAR-ready lines harvested while building

1. (2026-07-22) "I read RBI's TAT harmonisation circular at clause level and encoded
   its annex as a tested rules engine — every deadline and the ₹100/day suo-moto
   compensation — so the regulation itself became executable, verifiable code."

2. (2026-07-22) "When the regulation was ambiguous — calendar versus working days —
   I didn't guess silently; I documented the interpretation, the supporting clause,
   and the residual risk in a decision log, the way a compliance function would."

3. (2026-07-22) "I can explain why one failed payment can fall under three different
   RBI compensation regimes — flat ₹100/day under the 2019 TAT circular, penal
   interest at repo+2% for NEFT under the 2010 circular, or the underlying rail's
   rule for wallet off-us transactions."

4. (2026-07-22) "Where the data was ambiguous — you can't always tell a UPI merchant
   payment from a person-to-person one — I chose the conservative reading that
   produces a smaller but undisputable claim, and documented the trade-off: a
   disputed ₹500 claim is worth less than an undisputable ₹300 one."

5. (2026-07-22) "I normalized every bank's statement dialect into one canonical
   transaction schema, so adding a new bank means writing one parser — nothing
   downstream knows or cares which bank the data came from."

6. (2026-07-23) "Before building the detector, I built the exam it has to pass:
   synthetic statements with planted failures and one false-positive trap — a
   genuine merchant refund that looks identical to a failed-transaction reversal —
   graded as precision and recall."

7. (2026-07-23) "I designed v1 around data minimisation — the app asks for nothing
   a scammer would want — but architected the schema so RBI's Account Aggregator
   rail can plug in as just another parser when the product justifies
   regulated-entity status."

---

8. (2026-07-24) "The first real bank statement broke my core assumption: SBI
   issues reversals under a fresh reference number, not the original payment's,
   so reference-matching was structurally blind to every SBI failure. I only
   found it by testing on real data — then added amount-and-timing fallback
   matching, keeping inferred late matches behind user confirmation so the tool
   never fabricates a claim."

9. (2026-07-24) "My first real audit correctly returned zero owed — and that's a
   feature: the tool found the one reversal in the statement, classified it
   on-time, and I could trust the zero because the detector demonstrably works,
   not because it stayed silent."

---

## The "isn't this trivial?" defense (memorize the flow, not the words)

When an interviewer says *"this is just date subtraction × ₹100"* — concede, then flip:

**Concede:** "You're right — the arithmetic is trivial. Interest has been P×R×T for
centuries, yet banks employ thousands of reconciliation staff. The value was never
the multiplication; it's three things around it."

**The three things:**
1. **You can't calculate what you haven't found.** Nobody remembers a failed debit
   from months ago; the refund arrives days later, worded differently, different ref
   format. Finding failures across 2,000+ messy statement lines IS the product —
   the calculator is 5 lines, the detective is the project (measured with
   precision/recall against planted ground truth).
2. **You must know WHICH rule applies.** Three regimes: ₹100/day (2019 TAT circular,
   UPI/IMPS/cards/ATM), repo+2% penal interest (NEFT, 2010 circular), inherited-rail
   rule (wallet off-us). I mixed them up myself once WHILE building this — that slip
   is the proof ordinary customers can't self-serve. Encode once, cite clauses, done.
3. **Knowing you're owed ₹700 recovers ₹0.** Recovery needs the complaint pack:
   clause citation, evidence table, 30-day escalation clock, ombudsman filing.

**The proofs, ascending:**
- Market: RBI's suo-motu clause is near-universally unpaid and no product audits it.
  Counter-question: "If it's trivial, why does no bank pay automatically and no app check?"
- Analogy: tax refunds are "just arithmetic" too — ClearTax/TurboTax exist because
  the value is finding what applies, at scale, in a filing that survives scrutiny.
- Demo (the closer): 2,000 lines in → "4 incidents you never noticed, ₹1,400 owed,
  letter ready" in seconds. Post-Phase 6: "recovered actual rupees for my family."

**What they're really grading:** primary-source regulation read faithfully, three
regimes kept straight, conservative documented judgment calls (D5), self-measured
accuracy, CI discipline — the working skills of a RegTech/FinCrime analyst. The
₹100 is just the excuse to demonstrate them.
