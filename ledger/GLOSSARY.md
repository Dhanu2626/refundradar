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
