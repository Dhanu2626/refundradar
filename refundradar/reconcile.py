"""Match failed debits to their reversals and classify every incident.

What a statement alone can prove:
  - a debit that came back with reversal language -> failed txn (on time or late)
  - a debit that came back with refund language -> genuine merchant refund, excluded
  - a debit that came back with neither, both, or a bare RETURN -> needs the
    user's yes/no (DECISIONS.md, D11)
A debit that never came back looks identical to a successful payment, so
never-refunded failures require user confirmation (DECISIONS.md, D6) —
passed in as confirmed_failed_refs.

Matching passes (DECISIONS.md, D12): (1) a reference printed on both rows,
which proves the link only if no other payment carries that reference;
(2) for a payment the user confirmed failed, the single reversal-worded
credit of the same amount after it; (3) an amount+timing fallback for banks
like SBI that issue reversals under a fresh reference (D9). Anything short
of proof is asked, never claimed: a late link from (3), a reference shared
by several payments, a confirmed failure with competing credits. Each credit
settles one debit only.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date

from refundradar.model import Transaction, UNSUPPORTED_CHANNELS
from refundradar.rules_engine import Ruling, evaluate

REFUND_WORDS = ("REFUND", "CASHBACK")
# RETURN alone decides nothing: a returned order and a payment returned
# unpaid both say it (DECISIONS.md, D11).
RETURN_WORD = "RETURN"
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
    # "RETURNED TO SENDER" is a reversal phrase in its own right
    returned = RETURN_WORD in n.replace("RETURNED TO SENDER", "")
    if refund and not reversal:
        return "refund"
    if reversal and not refund and not returned:
        return "reversal"
    # both kinds of wording ("REFUND OF FAILED TXN"), a bare RETURN, or
    # neither: a question for the user, not a verdict (DECISIONS.md, D11)
    return "ambiguous"


def _ref_keys(t: Transaction) -> set[str]:
    return {r for r in (t.ref, t.alt_ref) if r}


def _supported(t: Transaction) -> bool:
    return t.channel is not None and t.channel not in UNSUPPORTED_CHANNELS


def _near(d: Transaction, c: Transaction) -> bool:
    return (c.txn_date - d.txn_date).days <= REVERSAL_WINDOW_DAYS


def _same_row(t: Transaction) -> tuple:
    return (t.txn_date, t.amount, t.is_debit, t.narration, t.ref, t.alt_ref)


def _take(c: Transaction, pool: list[Transaction], used: set) -> None:
    """Mark a credit used, with any exact copy of its row: the same refund
    exported twice is still one refund."""
    used.update(id(o) for o in pool if _same_row(o) == _same_row(c))


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
            _take(c, credits, used)


def reconcile(
    transactions: list[Transaction],
    confirmed_failed_refs: set[str] | None = None,
    as_of: date | None = None,
) -> list[Incident]:
    confirmed = confirmed_failed_refs or set()
    debits = [t for t in transactions if t.is_debit]
    credits = [t for t in transactions if not t.is_debit]
    used: set[int] = set()
    # A reference carried by more than one payment can't say which of them a
    # reversal belongs to: it links rows but proves nothing (D12).
    holders = Counter(k for d in debits for k in _ref_keys(d))
    is_confirmed = lambda d: bool(_ref_keys(d) & confirmed)
    shared = lambda d: any(holders[k] > 1 for k in _ref_keys(d))

    by_ref: dict[int, Transaction] = {}
    _pair(credits, debits, lambda d, c: _ref_keys(d) & _ref_keys(c), by_ref, used)
    settled, unresolved = _settle_confirmed(
        [d for d in debits if id(d) not in by_ref and is_confirmed(d)
         and _supported(d) and not shared(d)],
        credits, used)
    claimed = set(by_ref) | {id(d) for d in debits if is_confirmed(d)}
    fallback = _fallback_match_reversals(debits, credits, claimed, used)

    incidents = []
    for d in debits:
        match = by_ref.get(id(d))
        if match is not None:
            proven = any(holders[k] == 1 for k in _ref_keys(d) & _ref_keys(match))
            incidents.append(_by_reference(d, match, is_confirmed(d), proven))
        elif is_confirmed(d):
            incidents.append(_confirmed_failure(
                d, shared(d), settled.get(id(d)), unresolved.get(id(d), []), as_of))
    return incidents + fallback


def _by_reference(d: Transaction, c: Transaction, confirmed: bool, proven: bool) -> Incident:
    """Classify a debit whose reference reappears on credit c."""
    lang = _language(c.narration)
    if lang == "ambiguous" and confirmed:
        lang = "reversal"
    if lang == "refund":
        return Incident(
            d, EXCLUDED, None,
            "Money came back, but the wording says merchant refund "
            "(returned order), not a failed-transaction reversal — "
            "no compensation applies.",
            refund_date=c.txn_date,
        )
    if lang == "ambiguous":
        return Incident(
            d, CONFIRM, None,
            "Money came back with the same reference, but the wording "
            "doesn't clearly say the original payment failed — "
            "confirm before claiming.",
            refund_date=c.txn_date,
        )
    if not _supported(d):
        return Incident(
            d, UNSUPPORTED, None,
            f"Reversal found, but channel {d.channel!r} is outside "
            "the 2019 TAT circular (see DECISIONS.md D2).",
            refund_date=c.txn_date,
        )
    ruling = evaluate(d.channel, d.txn_date, c.txn_date)
    if ruling.on_time:
        return Incident(d, ON_TIME, ruling,
                        "Failed transaction, reversed within the deadline.",
                        refund_date=c.txn_date)
    if not (proven or confirmed):
        return Incident(
            d, CONFIRM, None,
            f"A reversal carrying this payment's reference came back "
            f"{ruling.days_late} days past the deadline, but other payments on "
            "this statement carry the same reference, so it doesn't prove "
            "which one failed — confirm before claiming.",
            refund_date=c.txn_date,
        )
    return Incident(
        d, LATE, ruling,
        f"Failed transaction, reversed {ruling.days_late} days past the deadline.",
        refund_date=c.txn_date,
    )


def _settle_confirmed(open_confirmed, credits, used) -> tuple[dict, dict]:
    """Find the refund of each confirmed failure no reference ties to a credit.

    Candidates are the unexplained credits of the same amount on or after the
    payment, whatever their wording. Only a single reversal-worded candidate
    that no other confirmed payment could also claim is taken as the refund;
    no candidate at all means never refunded; anything else stays a question
    (DECISIONS.md, D12).
    """
    def candidates(d):
        seen, out = set(), []
        for c in credits:
            if (id(c) not in used and c.amount == d.amount
                    and c.txn_date >= d.txn_date and _same_row(c) not in seen):
                seen.add(_same_row(c))
                out.append(c)
        return out

    cands = {id(d): candidates(d) for d in open_confirmed}
    contested = Counter(_same_row(c) for cs in cands.values() for c in cs)
    settled, unresolved = {}, {}
    for d in open_confirmed:
        cs = cands[id(d)]
        if (len(cs) == 1 and _language(cs[0].narration) == "reversal"
                and contested[_same_row(cs[0])] == 1):
            settled[id(d)] = cs[0]
            _take(cs[0], credits, used)
        elif cs:
            unresolved[id(d)] = cs
    return settled, unresolved


def _confirmed_failure(d, shared: bool, refund, candidates, as_of) -> Incident:
    """Classify a payment the user confirmed failed, with no same-reference credit."""
    if not _supported(d):
        return Incident(
            d, UNSUPPORTED, None,
            f"Confirmed failed, but channel {d.channel!r} is outside "
            "the 2019 TAT circular.",
        )
    if shared:
        return Incident(
            d, CONFIRM, None,
            "You confirmed a payment with this reference failed, but other "
            "payments on this statement carry the same reference, so "
            "RefundRadar can't tell which one you meant. Nothing is claimed "
            "for it.",
        )
    if refund is not None:
        ruling = evaluate(d.channel, d.txn_date, refund.txn_date)
        return Incident(
            d, ON_TIME if ruling.on_time else LATE, ruling,
            "You confirmed this payment failed; the only credit of the same "
            "amount after it is a reversal under a new reference, which came "
            "back " + ("within the deadline."
                       if ruling.on_time
                       else f"{ruling.days_late} days past the deadline."),
            refund_date=refund.txn_date,
        )
    if candidates:
        dates = ", ".join(c.txn_date.isoformat() for c in candidates[:3])
        more = " and more" if len(candidates) > 3 else ""
        what = ("a credit of the same amount came back" if len(candidates) == 1
                else "credits of the same amount came back")
        return Incident(
            d, CONFIRM, None,
            f"You confirmed this payment failed, and {what} after it "
            f"({dates}{more}) under another reference. RefundRadar can't tell "
            "whether that was the refund, so nothing is claimed until you "
            "check.",
            refund_date=candidates[0].txn_date if len(candidates) == 1 else None,
        )
    ruling = evaluate(d.channel, d.txn_date, None, as_of=as_of)
    return Incident(
        d, NEVER, ruling,
        "You confirmed this payment failed and no refund row "
        "exists — compensation accrues every day until reversal.",
    )


def _fallback_match_reversals(
    debits: list[Transaction],
    credits: list[Transaction],
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
    A reversal beyond the window is only asked about, and only when exactly
    one payment could be its origin (D12).
    """
    reversals = [c for c in credits if _language(c.narration) == "reversal"]
    open_debits = [d for d in debits if id(d) not in claimed and _supported(d)]
    pairs: dict[int, Transaction] = {}
    _pair(reversals, open_debits, _near, pairs, used)
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
    for c in sorted(reversals, key=lambda t: t.txn_date):
        if id(c) in used:
            continue
        origins = [d for d in open_debits if id(d) not in pairs
                   and d.amount == c.amount and d.txn_date <= c.txn_date]
        if len({_same_row(d) for d in origins}) != 1:
            continue  # none, or several payments it could belong to
        d = origins[0]
        pairs[id(d)] = c
        _take(c, reversals, used)
        ruling = evaluate(d.channel, d.txn_date, c.txn_date)
        out.append(Incident(
            d, CONFIRM, None,
            f"A reversal of the same amount came back "
            f"{(c.txn_date - d.txn_date).days} days after this payment under a "
            "different reference, and no other payment on this statement "
            "matches it. If this payment failed, that was its refund, "
            f"{ruling.days_late} days past the deadline — confirm before "
            "claiming.",
            refund_date=c.txn_date,
        ))
    return out
