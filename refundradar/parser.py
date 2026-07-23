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


def _amount(value) -> "Decimal | None":
    from decimal import Decimal, InvalidOperation
    text = str(value).replace(",", "").replace("₹", "").strip()
    if not text or text in ("-", "None"):
        return None
    try:
        d = Decimal(text)
    except InvalidOperation:
        return None
    return d if d != 0 else None


def parse_sbi_rows(rows: list[list]) -> list[Transaction]:
    """Map SBI's spreadsheet layout onto the canonical schema.

    SBI statements carry preamble rows (account holder, branch, period)
    before a header row like: Txn Date | Value Date | Description |
    Ref No./Cheque No. | Branch Code | Debit | Credit | Balance.
    Columns are located by header NAME, not position, so layout drift
    across portal versions doesn't break the mapping.
    """
    from refundradar.formats import _cell_date

    header_idx, cols = None, {}
    for idx, row in enumerate(rows):
        names = [str(c).strip().lower() if c is not None else "" for c in row]
        if any("date" in n for n in names) and any("debit" in n for n in names):
            for i, n in enumerate(names):
                if "txn date" in n or n == "date" or "transaction date" in n:
                    cols.setdefault("date", i)
                elif "description" in n or "narration" in n or "particulars" in n:
                    cols["narration"] = i
                elif "ref" in n or "cheque" in n:
                    cols["ref"] = i
                elif "debit" in n:
                    cols["debit"] = i
                elif "credit" in n:
                    cols["credit"] = i
                elif "balance" in n:
                    cols["balance"] = i
            if {"date", "narration", "debit", "credit"} <= set(cols):
                header_idx = idx
                break
            cols = {}
    if header_idx is None:
        raise ValueError(
            "Could not find SBI's transaction table header (Txn Date / "
            "Description / Debit / Credit) in this file."
        )

    txns = []
    for row in rows[header_idx + 1:]:
        get = lambda key: row[cols[key]] if key in cols and cols[key] < len(row) else None
        txn_date = _cell_date(get("date")) if get("date") is not None else None
        if txn_date is None:
            continue
        debit, credit = _amount(get("debit")), _amount(get("credit"))
        if debit is None and credit is None:
            continue
        narration = str(get("narration") or "").strip()
        t = make_transaction(txn_date, debit if debit is not None else credit,
                             debit is not None, narration,
                             balance=_amount(get("balance")), bank="SBI")
        ref_cell = str(get("ref") or "").strip()
        if ref_cell and ref_cell.upper() not in ("", "-", "NONE", "TRANSFER TO", "TRANSFER FROM"):
            if t.ref is None:
                t.ref = ref_cell
        txns.append(t)
    return txns


def parse_statement_file(
    path: str | Path, password: str | None = None
) -> list[Transaction]:
    """Open any supported statement file: CSV, xlsx, xls, or encrypted."""
    from refundradar.formats import load_rows, sniff

    data = Path(path).read_bytes()
    if sniff(data) == "text":
        text = data.decode("utf-8-sig", errors="replace")
        try:
            return parse_generic_csv_text(text)
        except ValueError:
            rows = list(csv.reader(io.StringIO(text)))
            return parse_sbi_rows(rows)
    return parse_sbi_rows(load_rows(data, password=password))
