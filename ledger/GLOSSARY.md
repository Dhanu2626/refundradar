# Glossary — FCC/payments terms met while building

- **TAT (Turn Around Time)** — the regulatory deadline for resolving something; here,
  the auto-reversal deadline for failed transactions (RBI/2019-20/67).
- **T+n** — n calendar days after transaction day T (the circular defines T as calendar date).
- **Suo moto** — "on its own motion": the bank must pay compensation automatically,
  without the customer complaining. The clause nobody enforces — our whole product.
- **Auto-reversal** — the bank returning a failed debit to the customer without being asked.
- **P2P vs P2M** — person-to-person vs person-to-merchant payment; different TAT deadlines
  because merchant flows have a longer confirmation chain.
- **UTR / RRN** — Unique Transaction Reference / Retrieval Reference Number: the IDs that
  let you match a debit to its refund (Phase 2's whole job).
- **Charge-slip** — the merchant-side confirmation a PoS transaction completed; its absence
  while the account is debited = the PoS failure scenario.
- **AePS / APBS** — Aadhaar-enabled Payment System / Aadhaar Payment Bridge (subsidy credits).
- **NACH** — National Automated Clearing House: mandates/auto-debits (EMIs, SIPs); debiting
  after a revoked mandate is itself a violation with T+1 reversal.
- **PPI** — Prepaid Payment Instrument (wallets, prepaid cards); "on-us" = both legs inside
  the same PPI issuer.
- **RBI Ombudsman (RB-IOS)** — free RBI grievance body; escalation path when the bank
  ignores a complaint for 30 days. Filed via the CMS portal.
- **LAF Repo Rate** — the rate at which RBI lends to banks (Liquidity Adjustment
  Facility); NEFT delay compensation is penal interest at repo + 2%.
- **Penal interest** — interest paid as a penalty for delay (NEFT regime), as opposed
  to the flat ₹100/day of the TAT circular.
- **Batch settlement** — NEFT processes in half-hourly batches (not real-time like
  IMPS/UPI); its 2-hour credit/return clock starts at batch settlement.
- **On-us / off-us** — whether both legs of a transaction stay inside one institution
  (on-us) or cross to another via a rail like UPI/card network (off-us).
- **Decision log / ADR** — a file recording each judgment call with reasoning and
  residual risk; standard practice in regulated software (see rules/DECISIONS.md).
- **Narration** — the free-text description on a statement line
  (`UPI/DR/519912345678/...`); every bank writes it in its own dialect.
- **VPA (Virtual Payment Address)** — a UPI handle like `name@okhdfc`; phone-number
  VPAs signal a person, QR/gateway VPAs signal a merchant.
- **RRN (Retrieval Reference Number)** — 12-digit reference on UPI/IMPS/card
  transactions; our primary key for matching a debit to its refund.
- **Canonical schema** — one standard internal format all inputs are converted to,
  so downstream code never deals with per-bank differences.
- **Decimal vs float** — money math must use exact decimal arithmetic; binary
  floats can't represent 0.1 and drift by paise.
