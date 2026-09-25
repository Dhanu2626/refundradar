"""Aggregate reconciliation results into the audit a customer actually reads."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from refundradar.model import Transaction
from refundradar.parser import parse_generic_csv_text
from refundradar.reconcile import LATE, NEVER, ON_TIME, Incident, reconcile


@dataclass
class Audit:
    incidents: list[Incident]
    as_of: date
    total_owed_inr: int = 0
    stuck_amount: Decimal = Decimal(0)
    on_time_count: int = 0
    statement_lines: int = 0

    def __post_init__(self):
        for i in self.incidents:
            if i.status in (LATE, NEVER):
                if (self.as_of - i.txn.txn_date).days > 365:
                    i.time_barred = True  # D8: out of the headline, into a warning
                    continue
                if i.ruling:
                    self.total_owed_inr += i.ruling.compensation_inr
                if i.status == NEVER:
                    self.stuck_amount += i.txn.amount
            if i.status == ON_TIME:
                self.on_time_count += 1

    def claimable(self) -> list[Incident]:
        return [i for i in self.incidents
                if i.status in (LATE, NEVER) and not i.time_barred]


def build_audit(
    transactions: list[Transaction],
    confirmed_failed_refs: set[str] | None = None,
    as_of: date | None = None,
    confirmed_refunds: list[tuple[Transaction, Transaction]] | None = None,
) -> Audit:
    as_of = as_of or date.today()
    incidents = reconcile(transactions, confirmed_failed_refs, as_of=as_of,
                          confirmed_refunds=confirmed_refunds)
    return Audit(incidents, as_of, statement_lines=len(transactions))


def audit_csv_text(
    csv_text: str,
    confirmed_failed_refs: set[str] | None = None,
    as_of: date | None = None,
) -> Audit:
    return build_audit(parse_generic_csv_text(csv_text), confirmed_failed_refs, as_of)


def to_dict(a: Audit) -> dict:
    def inc(i: Incident) -> dict:
        return {
            "status": i.status,
            "time_barred": i.time_barred,
            "reason": i.reason,
            "date": i.txn.txn_date.isoformat(),
            "amount": str(i.txn.amount),
            "narration": i.txn.narration,
            "ref": i.txn.ref,
            "channel": i.txn.channel,
            "channel_name": i.ruling.channel_name if i.ruling else None,
            "deadline": i.ruling.deadline.isoformat() if i.ruling else None,
            "refund_date": i.refund_date.isoformat() if i.refund_date else None,
            "days_late": i.ruling.days_late if i.ruling else None,
            "compensation_inr": i.ruling.compensation_inr if i.ruling else None,
            "citation": i.ruling.citation if i.ruling else None,
        }

    return {
        "as_of": a.as_of.isoformat(),
        "statement_lines": a.statement_lines,
        "total_owed_inr": a.total_owed_inr,
        "stuck_amount": str(a.stuck_amount),
        "on_time_count": a.on_time_count,
        "incidents": [inc(i) for i in a.incidents],
    }
