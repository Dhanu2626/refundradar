"""Read a statement export into canonical Transactions.

v1 supports the generic CSV format used by samples/ (Date,Narration,Ref,
Debit,Credit,Balance with dd-mm-yyyy dates). Each real bank's export gets
its own small reader later; all of them normalize into the same schema so
nothing downstream cares where the data came from.
"""

import csv
import io
from datetime import datetime
from pathlib import Path

from refundradar.model import Transaction, make_transaction


def parse_generic_csv_text(text: str) -> list[Transaction]:
    txns = []
    reader = csv.DictReader(io.StringIO(text))
    required = {"Date", "Narration", "Debit", "Credit"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ValueError(
            "Unrecognized statement format. Expected CSV columns: "
            "Date, Narration, Ref, Debit, Credit, Balance"
        )
    for row in reader:
        debit_cell = (row.get("Debit") or "").strip()
        credit_cell = (row.get("Credit") or "").strip()
        if not debit_cell and not credit_cell:
            continue
        is_debit = bool(debit_cell)
        t = make_transaction(
            datetime.strptime(row["Date"].strip(), "%d-%m-%Y").date(),
            debit_cell if is_debit else credit_cell,
            is_debit,
            (row.get("Narration") or "").strip(),
            balance=(row.get("Balance") or "").strip() or None,
            bank="generic",
        )
        explicit_ref = (row.get("Ref") or "").strip()
        if explicit_ref:
            t.ref = explicit_ref
        txns.append(t)
    return txns


def parse_generic_csv(path: str | Path) -> list[Transaction]:
    return parse_generic_csv_text(Path(path).read_text(encoding="utf-8-sig"))
