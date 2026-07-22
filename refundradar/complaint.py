"""Turn an audit into the complaint pack: bank letter + ombudsman draft.

Output is markdown the customer can paste into an email or print. Tone is
firm, factual, and clause-cited — the letter a grievance cell can't wave away.
"""

from datetime import timedelta

from refundradar.audit import Audit
from refundradar.reconcile import LATE, NEVER
from refundradar.rules_engine import CIRCULAR

OMBUDSMAN_PORTAL = "https://cms.rbi.org.in"


def generate_complaint_pack(
    audit: Audit,
    customer_name: str,
    account_last4: str,
    contact: str,
    bank_name: str = "The Branch Manager / Grievance Redressal Cell",
) -> str:
    claim = audit.claimable()
    if not claim:
        return "No claimable incidents in this audit — nothing to complain about."

    lines = [
        f"# Complaint pack — generated {audit.as_of.isoformat()} by RefundRadar",
        "",
        "## Part 1 — Grievance letter to the bank",
        "",
        f"To: {bank_name}",
        f"From: {customer_name} (account ending {account_last4})",
        f"Contact: {contact}",
        f"Date: {audit.as_of.isoformat()}",
        "",
        "Subject: Claim of customer compensation for delayed reversal of failed "
        f"transactions under {CIRCULAR}",
        "",
        "Dear Sir/Madam,",
        "",
        "The RBI circular cited above harmonises the turn-around time for the "
        "reversal of failed transactions and mandates compensation of Rs.100 per "
        "day of delay, payable suo moto — without the customer having to ask.",
        "",
        "An audit of my account statement shows the following failed transactions "
        "where the mandated deadline was not met:",
        "",
        "| # | Date | Channel | Amount (Rs.) | Reference | Reversal deadline | "
        "Reversed on | Days late | Compensation due (Rs.) |",
        "|---|------|---------|--------------|-----------|-------------------|"
        "-------------|-----------|------------------------|",
    ]
    for n, i in enumerate(claim, 1):
        r = i.ruling
        reversed_on = i.refund_date.isoformat() if i.refund_date else "NOT YET REVERSED"
        lines.append(
            f"| {n} | {i.txn.txn_date.isoformat()} | {r.channel_name} | "
            f"{i.txn.amount} | {i.txn.ref} | {r.deadline.isoformat()} | "
            f"{reversed_on} | {r.days_late} | {r.compensation_inr} |"
        )

    unreversed = [i for i in claim if i.status == NEVER]
    lines += [
        "",
        f"**Total compensation due as of {audit.as_of.isoformat()}: "
        f"Rs.{audit.total_owed_inr}**"
        + (f", plus Rs.{sum(i.txn.amount for i in unreversed)} of principal still "
           "not reversed, with compensation continuing to accrue at Rs.100/day "
           "per incident until reversal." if unreversed else "."),
        "",
        "I request that (a) any unreversed principal be credited immediately, and "
        "(b) the compensation above be credited to my account within 7 working "
        "days, failing which I will escalate to the RBI Ombudsman under the "
        "Integrated Ombudsman Scheme, 2021.",
        "",
        "Yours faithfully,",
        customer_name,
        "",
        "## Part 2 — Escalation timeline",
        "",
        f"- {audit.as_of.isoformat()} — letter submitted to the bank",
        f"- {(audit.as_of + timedelta(days=30)).isoformat()} — if no satisfactory "
        "resolution by this date, the RBI Ombudsman route unlocks",
        "",
        "## Part 3 — RBI Ombudsman draft (use only after 30 days or rejection)",
        "",
        f"File online at {OMBUDSMAN_PORTAL} (no fee, no lawyer needed).",
        "",
        "Suggested complaint text:",
        "",
        f"> I hold an account ending {account_last4}. The failed transactions "
        "listed in the attached table were not reversed within the TAT mandated "
        f"by {CIRCULAR}, and the compensation of Rs.100/day payable suo moto "
        "under the same circular was not credited. I complained to my bank on "
        f"{audit.as_of.isoformat()} and did not receive resolution within 30 "
        "days. I request the reversal of any outstanding principal and payment "
        f"of compensation totalling Rs.{audit.total_owed_inr} (as of "
        f"{audit.as_of.isoformat()}, still accruing for unreversed items).",
        "",
        "Attach: the evidence table above and your account statement for the "
        "relevant period.",
    ]
    citations = sorted({i.ruling.citation for i in claim})
    lines += ["", "## Citations", ""] + [f"- {c}" for c in citations]
    return "\n".join(lines)
