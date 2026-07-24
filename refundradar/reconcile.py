"""Match failed debits to their reversals and classify every incident.

What a statement alone can prove:
  - a debit that came back with reversal language -> failed txn (on time or late)
  - a debit that came back with refund language -> genuine merchant refund, excluded
  - a debit that came back with neither -> needs the user's yes/no
A debit that never came back looks identical to a successful payment, so
never-refunded failures require user confirmation (DECISIONS.md, D6) —
passed in as confirmed_failed_refs.

Two matching passes: (1) exact reference match, then (2) an amount+timing
fallback for banks like SBI that issue reversals under a fresh reference
(DECISIONS.md, D9). The fallback never auto-claims a late reversal — inferred
links are downgraded to needs_confirmation.
"""

from dataclasses import dataclass
from datetime import date

from refundradar.model import Transaction, UNSUPPORTED_CHANNELS
from refundradar.rules_engine import Ruling, evaluate

REFUND_WORDS = ("REFUND", "RETURN", "CASHBACK")
# "UPI/REF" is SBI's marker for a reversal credit — and SBI issues it with a
# FRESH reference, not the original payment's, so ref-matching can't tie it
# back (field-tested 2026-07-24). The amount+window fallback pass handles it.
REVERSAL_WORDS = ("REVERSAL", "REV OF", "UPI/REF", "FAILED", "NOT DISPENSED",
                  "DECLINED", "RETURNED TO SENDER")

# Amount+time fallback: how many days after a debit a reversal may appear.
REVERSAL_WINDOW_DAYS = 10

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
    claimed_debit_ids: set[int] = set()
    used_credit_ids: set[int] = set()
    for d in (t for t in transactions if t.is_debit and t.ref):
        match = next(
            (c for c in credits.get(d.ref, [])
             if c.amount == d.amount and c.txn_date >= d.txn_date),
            None,
        )
        if match is not None:
            claimed_debit_ids.add(id(d))
            used_credit_ids.add(id(match))
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
            claimed_debit_ids.add(id(d))
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

    incidents += _fallback_match_reversals(
        transactions, claimed_debit_ids, used_credit_ids
    )
    return incidents


def _fallback_match_reversals(
    transactions: list[Transaction],
    claimed_debit_ids: set[int],
    used_credit_ids: set[int],
) -> list[Incident]:
    """Catch reversals that carry a fresh reference (SBI-style).

    A reversal-worded credit that no reference tied to a debit is matched to
    the CLOSEST-in-time unclaimed debit of the same amount within the window.
    Because the link is inferred, not proven by a shared reference:
      - if the inferred pairing is on time (Rs.0 at stake) we record it as such;
      - if it looks late (money would be claimed) we downgrade to
        needs_confirmation, never an automatic claim (DECISIONS.md, D6/D9).
    """
    debits = [t for t in transactions if t.is_debit and id(t) not in claimed_debit_ids]
    out = []
    for c in transactions:
        if c.is_debit or id(c) in used_credit_ids:
            continue
        if _language(c.narration) != "reversal":
            continue
        cands = sorted(
            (d for d in debits
             if d.amount == c.amount
             and 0 <= (c.txn_date - d.txn_date).days <= REVERSAL_WINDOW_DAYS
             and id(d) not in claimed_debit_ids
             and d.channel not in UNSUPPORTED_CHANNELS and d.channel is not None),
            key=lambda d: (c.txn_date - d.txn_date).days,
        )
        if not cands:
            continue
        d = cands[0]
        claimed_debit_ids.add(id(d))
        used_credit_ids.add(id(c))
        ruling = evaluate(d.channel, d.txn_date, c.txn_date)
        if ruling.on_time:
            out.append(Incident(
                d, ON_TIME, ruling,
                "Reversal matched by amount and timing (your bank reverses with "
                "a new reference) — completed within the deadline.",
                refund_date=c.txn_date,
            ))
        else:
            out.append(Incident(
                d, CONFIRM, None,
                f"A reversal of the same amount appeared {ruling.days_late} days "
                "past the deadline, but your bank issues reversals with a fresh "
                "reference, so this link is inferred from amount and timing. "
                "Confirm this pairing before claiming.",
                refund_date=c.txn_date,
            ))
    return out
