"""Apply RBI/2019-20/67 (TAT harmonisation) to a single failed transaction.

Given the payment channel, the transaction date, and the refund date (if any),
compute the reversal deadline and the suo-moto compensation the bank owes.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

RULES_FILE = Path(__file__).resolve().parent.parent / "rules" / "rbi_tat.yaml"

CIRCULAR = "RBI/2019-20/67 (DPSS.CO.PD No.629/02.01.014/2019-20) dated 20-09-2019"


@dataclass(frozen=True)
class Ruling:
    """Outcome of applying the circular to one failed transaction."""

    channel: str
    channel_name: str
    txn_date: date
    deadline: date          # bank must auto-reverse by end of this calendar date
    refund_date: date | None
    refunded: bool
    on_time: bool
    days_late: int          # days beyond the deadline (0 if on time)
    compensation_inr: int   # ₹100 x days_late, owed suo moto
    citation: str


def load_rules(path: Path = RULES_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    rules["by_code"] = {c["code"]: c for c in rules["channels"]}
    return rules


def evaluate(
    channel: str,
    txn_date: date,
    refund_date: date | None = None,
    as_of: date | None = None,
    rules: dict | None = None,
) -> Ruling:
    """Judge one failed transaction against the circular.

    as_of: for still-unrefunded transactions, the date up to which
    compensation has accrued (defaults to today).
    """
    rules = rules or load_rules()
    try:
        rule = rules["by_code"][channel]
    except KeyError:
        known = ", ".join(sorted(rules["by_code"]))
        raise KeyError(f"Unknown channel {channel!r}. Known channels: {known}") from None

    deadline = txn_date + timedelta(days=rule["reversal_deadline_days"])
    per_day = rules["compensation_per_day_inr"]

    if refund_date is not None:
        days_late = max((refund_date - deadline).days, 0)
    else:
        as_of = as_of or date.today()
        days_late = max((as_of - deadline).days, 0)

    return Ruling(
        channel=channel,
        channel_name=rule["name"],
        txn_date=txn_date,
        deadline=deadline,
        refund_date=refund_date,
        refunded=refund_date is not None,
        on_time=refund_date is not None and days_late == 0,
        days_late=days_late,
        compensation_inr=days_late * per_day,
        citation=f"{CIRCULAR}, Annex: {rule['name']} — reversal by T+{rule['reversal_deadline_days']}",
    )
