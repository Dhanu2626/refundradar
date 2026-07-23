"""Match failed debits to their reversals and classify every incident.

What a statement alone can prove:
  - a debit that came back with reversal language -> failed txn (on time or late)
  - a debit that came back with refund language -> genuine merchant refund, excluded
  - a debit that came back with neither -> needs the user's yes/no
A debit that never came back looks identical to a successful payment, so
never-refunded failures require user confirmation (DECISIONS.md, D6) —
passed in as confirmed_failed_refs.
"""

from dataclasses import dataclass
from datetime import date

from refundradar.model import Transaction, UNSUPPORTED_CHANNELS
from refundradar.rules_engine import Ruling, evaluate

REFUND_WORDS = ("REFUND", "RETURN", "CASHBACK")
REVERSAL_WORDS = ("REV", "REVERSAL", "FAILED", "NOT DISPENSED", "DECLINED")

ON_TIME = "refunded_on_time"
LATE = "refunded_late"
NEVER = "never_refunded"
EXCLUDED = "excluded_genuine_refund"
CONFIRM = "needs_confirmation"
UNSUPPORTED = "unsupported_channel"


@dataclass
class Incident:
    txn: Transaction
    status: str
    ruling: Ruling | None
    reason: str
    refund_date: date | None = None
    time_barred: bool = False  # set by the audit layer (DECISIONS.md, D8)


def _language(narration: str) -> str:
    n = narration.upper()
    if any(w in n for w in REFUND_WORDS):
        return "refund"
    if any(w in n for w in REVERSAL_WORDS):
        return "reversal"
    return "ambiguous"


def reconcile(
    transactions: list[Transaction],
    confirmed_failed_refs: set[str] | None = None,
    as_of: date | None = None,
) -> list[Incident]:
    confirmed = confirmed_failed_refs or set()
    credits: dict[str, list[Transaction]] = {}
    for t in transactions:
        if not t.is_debit and t.ref:
            credits.setdefault(t.ref, []).append(t)

    incidents = []
    for d in (t for t in transactions if t.is_debit and t.ref):
        match = next(
            (c for c in credits.get(d.ref, [])
             if c.amount == d.amount and c.txn_date >= d.txn_date),
            None,
        )
        if match is not None:
            lang = _language(match.narration)
            if lang == "ambiguous" and d.ref in confirmed:
                lang = "reversal"
            if lang == "refund":
                incidents.append(Incident(
                    d, EXCLUDED, None,
                    "Money came back, but the wording says merchant refund "
                    "(returned order), not a failed-transaction reversal — "
                    "no compensation applies.",
                    refund_date=match.txn_date,
                ))
            elif lang == "reversal":
                if d.channel in UNSUPPORTED_CHANNELS or d.channel is None:
                    incidents.append(Incident(
                        d, UNSUPPORTED, None,
                        f"Reversal found, but channel {d.channel!r} is outside "
                        "the 2019 TAT circular (see DECISIONS.md D2).",
                        refund_date=match.txn_date,
                    ))
                else:
                    ruling = evaluate(d.channel, d.txn_date, match.txn_date)
                    incidents.append(Incident(
                        d, ON_TIME if ruling.on_time else LATE, ruling,
                        "Failed transaction, reversed "
                        + ("within the deadline."
                           if ruling.on_time
                           else f"{ruling.days_late} days past the deadline."),
                        refund_date=match.txn_date,
                    ))
            else:
                incidents.append(Incident(
                    d, CONFIRM, None,
                    "Money came back with the same reference, but the wording "
                    "doesn't say whether the original payment failed — "
                    "confirm before claiming.",
                    refund_date=match.txn_date,
                ))
        elif d.ref in confirmed:
            if d.channel in UNSUPPORTED_CHANNELS or d.channel is None:
                incidents.append(Incident(
                    d, UNSUPPORTED, None,
                    f"Confirmed failed, but channel {d.channel!r} is outside "
                    "the 2019 TAT circular.",
                ))
            else:
                ruling = evaluate(d.channel, d.txn_date, None, as_of=as_of)
                incidents.append(Incident(
                    d, NEVER, ruling,
                    "You confirmed this payment failed and no refund row "
                    "exists — compensation accrues every day until reversal.",
                ))
    return incidents
