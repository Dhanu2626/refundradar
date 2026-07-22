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
