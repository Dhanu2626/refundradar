"""Match failed debits to their reversals and classify every incident.

What a statement alone can prove:
  - a debit that came back with reversal language -> failed txn (on time or late)
  - a debit that came back with refund language -> genuine merchant refund, excluded
  - a debit that came back with neither, or with both -> needs the user's yes/no
A debit that never came back looks identical to a successful payment, so
never-refunded failures require user confirmation (DECISIONS.md, D6) —
passed in as confirmed_failed_refs.

Matching passes: (1) a reference printed on both rows (either of a row's
references counts), then (2) for payments the user confirmed failed, a
reversal under a fresh reference, then (3) an amount+timing fallback for
banks like SBI that issue reversals under a fresh reference (DECISIONS.md,
D9). The fallback never auto-claims a late reversal — inferred links are
downgraded to needs_confirmation. Each credit settles one debit only (D12).
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
    refund = any(w in n for w in REFUND_WORDS)
    reversal = any(w in n for w in REVERSAL_WORDS)
    if refund and reversal:
        # "REFUND OF FAILED TXN", "RETURNED TO SENDER": wording that points
        # both ways is a question for the user, not a verdict (DECISIONS.md, D11)
        return "ambiguous"
    if refund:
        return "refund"
    if reversal:
        return "reversal"
    return "ambiguous"


def _ref_keys(t: Transaction) -> set[str]:
    return {r for r in (t.ref, t.alt_ref) if r}


def _supported(t: Transaction) -> bool:
    return t.channel is not None and t.channel not in UNSUPPORTED_CHANNELS


def _near(d: Transaction, c: Transaction) -> bool:
    return (c.txn_date - d.txn_date).days <= REVERSAL_WINDOW_DAYS


def _pair(credits, debits, fits, pairs: dict, used: set) -> None:
    """Give each credit, earliest first, to the closest earlier debit it fits.

    One credit settles one debit, so a duplicated row can't be claimed twice,
    and a reference reused across payments goes to the payment nearest the
    credit rather than the first one listed (DECISIONS.md, D12).
    """
    for c in sorted(credits, key=lambda t: t.txn_date):
        if id(c) in used:
            continue
        cands = [d for d in debits
                 if id(d) not in pairs and d.amount == c.amount
                 and d.txn_date <= c.txn_date and fits(d, c)]
        if cands:
            pairs[id(max(cands, key=lambda t: t.txn_date))] = c
            used.add(id(c))


def reconcile(
    transactions: list[Transaction],
    confirmed_failed_refs: set[str] | None = None,
    as_of: date | None = None,
) -> list[Incident]:
    confirmed = confirmed_failed_refs or set()
    debits = [t for t in transactions if t.is_debit]
    credits = [t for t in transactions if not t.is_debit]
    reversals = [c for c in credits if _language(c.narration) == "reversal"]
    used: set[int] = set()

    by_ref: dict[int, Transaction] = {}
    _pair(credits, debits, lambda d, c: _ref_keys(d) & _ref_keys(c), by_ref, used)

    # A payment the user confirmed failed, that no reference ties to a credit:
    # a nearby reversal under a new reference is its refund, and one further
    # away still rules out claiming it was never refunded (DECISIONS.md, D12).
    is_confirmed = lambda d: bool(_ref_keys(d) & confirmed)
    open_confirmed = [d for d in debits
                      if id(d) not in by_ref and is_confirmed(d) and _supported(d)]
    nearby: dict[int, Transaction] = {}
    _pair(reversals, open_confirmed, _near, nearby, used)
    claimed = set(by_ref) | {id(d) for d in debits if is_confirmed(d)}
    fallback = _fallback_match_reversals(debits, reversals, claimed, used)
    distant: dict[int, Transaction] = {}
    _pair(reversals, [d for d in open_confirmed if id(d) not in nearby],
          lambda d, c: True, distant, used)

    incidents = []
    for d in debits:
        match = by_ref.get(id(d))
        if match is not None:
            lang = _language(match.narration)
            if lang == "ambiguous" and is_confirmed(d):
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
                if not _supported(d):
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
                    "doesn't clearly say the original payment failed — "
                    "confirm before claiming.",
                    refund_date=match.txn_date,
                ))
        elif is_confirmed(d):
            if not _supported(d):
                incidents.append(Incident(
                    d, UNSUPPORTED, None,
                    f"Confirmed failed, but channel {d.channel!r} is outside "
                    "the 2019 TAT circular.",
                ))
            elif id(d) in nearby:
                c = nearby[id(d)]
                ruling = evaluate(d.channel, d.txn_date, c.txn_date)
                incidents.append(Incident(
                    d, ON_TIME if ruling.on_time else LATE, ruling,
                    "You confirmed this payment failed; a reversal of the same "
                    "amount came back under a new reference "
                    + ("within the deadline."
                       if ruling.on_time
                       else f"{ruling.days_late} days past the deadline."),
                    refund_date=c.txn_date,
                ))
            elif id(d) in distant:
                c = distant[id(d)]
                incidents.append(Incident(
                    d, CONFIRM, None,
                    "You confirmed this payment failed, and a reversal of the "
                    f"same amount came back {(c.txn_date - d.txn_date).days} "
                    "days later under a new reference — too far apart to link "
                    "without proof. If it was this refund, it came back late; "
                    "if not, this payment was never refunded. Check before "
                    "claiming either.",
                    refund_date=c.txn_date,
                ))
            else:
                ruling = evaluate(d.channel, d.txn_date, None, as_of=as_of)
                incidents.append(Incident(
                    d, NEVER, ruling,
                    "You confirmed this payment failed and no refund row "
                    "exists — compensation accrues every day until reversal.",
                ))
    return incidents + fallback


def _fallback_match_reversals(
    debits: list[Transaction],
    reversals: list[Transaction],
    claimed: set[int],
    used: set[int],
) -> list[Incident]:
    """Catch reversals that carry a fresh reference (SBI-style).

    A reversal-worded credit that no reference tied to a debit is matched to
    the CLOSEST-in-time unclaimed debit of the same amount within the window.
    Because the link is inferred, not proven by a shared reference:
      - if the inferred pairing is on time (Rs.0 at stake) we record it as such;
      - if it looks late (money would be claimed) we downgrade to
        needs_confirmation, never an automatic claim (DECISIONS.md, D6/D9).
    """
    pairs: dict[int, Transaction] = {}
    _pair(reversals, [d for d in debits if id(d) not in claimed],
          lambda d, c: _near(d, c) and _supported(d), pairs, used)
    by_id = {id(d): d for d in debits}
    out = []
    for d_id, c in pairs.items():
        d = by_id[d_id]
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
