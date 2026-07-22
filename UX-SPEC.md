# UX spec — how a real customer uses RefundRadar

The Phase 5 build contract. Design rule: if any step needs a manual, the design failed.

## The journey in one line

Drop one file → tap yes/no on anything we're unsure about → confirm three
pre-filled fields → get your letter.

## Screen 1 — the doorway

- One drop zone: "Drop your bank statement here."
- One trust line: "No login. No signup. Your statement never leaves this computer."
- "Try with a demo statement" button — see the product work on synthetic data
  BEFORE being asked to trust it with real data. Show, then ask.
- "How do I get my statement?" helper: pick your bank → screenshots of exactly
  where the CSV/Excel export hides in that bank's netbanking. For ordinary users
  this is the hardest step in the whole journey; treat it as a first-class feature.

## Screen 2 — the audit

- One number carries the story: "Your bank owes you ₹X" (see mockup).
- Each incident is one plain-English row: what you paid, when the refund was due,
  how late it was. Clause citations live one click deeper, where the letter needs them.
- Confirm, don't assume: when the reconciler is unsure ("₹2,000 to Swiggy on
  12 Mar — did this order actually go through?"), ask a yes/no question. Never
  silently put a doubtful claim into a legal letter.

## Screen 3 — the action

- One button: "Generate complaint pack."
- Only NOW ask for what the letter needs — name as on the account, last-4 of the
  account, contact for the bank's reply — all pre-filled from the statement header
  where possible, just confirmed by the user.
- Then show the escalation tracker: letter sent → bank has 30 days → ombudsman
  filing unlocks. The app walks the user to recovered money, not just information.

## Data stance — v1 vs v2 (decided 2026-07-23)

**v1 (this build): data minimisation as the moat.**
No login, no signup, no name/DOB/mobile collection, nothing stored server-side —
there is no server. The audit needs only the statement file, which already contains
every transaction. We never ask for anything a scammer would want, and that absence
of questions IS the trust signal. It also keeps us out of data-custodian
obligations (India's DPDP Act) that a one-person project has no business carrying.

**v2 (documented ambition, not built): Account Aggregator integration.**
RBI's AA framework (Sahamati ecosystem — Finvu, OneMoney, etc.) is the legal rail
for "connect your bank": the customer approves consent in their AA app (OTP goes
to the AA, never to us), and the bank ships encrypted history directly. Requires
registered Financial Information User status — i.e., a company, not a side project.
The architecture is already ready: to the engine, an AA feed is just one more
parser normalizing into the same canonical Transaction schema; nothing downstream
changes. When the product justifies regulated-entity status, this is a two-week
integration, not a rewrite.
