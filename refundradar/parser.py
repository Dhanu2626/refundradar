"""Read a statement export into canonical Transactions.

Supports the generic CSV format used by samples/demo_statement.csv (Date,
Narration,Ref,Debit,Credit,Balance with dd-mm-yyyy dates) plus bank exports:
SBI and HDFC each get a small row mapper. All of them normalize into the same
schema so nothing downstream cares where the data came from.
"""

import csv
import io
import re
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
                elif ("description" in n or "narration" in n
                      or "particulars" in n or "detail" in n):
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


def _hdfc_columns(row: list) -> dict[str, int] | None:
    """Column indexes if `row` is HDFC's transaction header, else None.

    HDFC's Excel export heads the table Date | Narration | Chq./Ref.No. |
    Value Dt | Withdrawal Amt. | Deposit Amt. | Closing Balance; its
    "Delimited" text export says Debit Amount / Credit Amount / Chq/Ref
    Number instead. "Narration" plus "Closing Balance" is a pairing SBI's
    layout never carries, which is what routes a file here.
    """
    cols = {}
    for i, cell in enumerate(row):
        n = str(cell).strip().lower() if cell is not None else ""
        if n == "date":
            cols.setdefault("date", i)
        elif "narration" in n:
            cols["narration"] = i
        elif "ref" in n:
            cols["ref"] = i
        elif "withdrawal" in n or "debit" in n:
            cols["debit"] = i
        elif "deposit" in n or "credit" in n:
            cols["credit"] = i
        elif "closing balance" in n:
            cols["balance"] = i
    if {"date", "narration", "debit", "credit", "balance"} <= set(cols):
        return cols
    return None


def _hdfc_ref(cell) -> str | None:
    """HDFC's Chq./Ref.No. cell as a reference, or None.

    HDFC left-pads a 12-digit UPI/IMPS RRN to 16 digits (0000603412345678);
    unpadding lines it up with the same RRN quoted in another row's
    narration. An all-zero cell means the row has no reference.
    """
    ref = str(cell or "").strip()
    if not ref.strip("0"):
        return None
    m = re.fullmatch(r"0000(\d{12})", ref)
    return m.group(1) if m else ref


def parse_hdfc_rows(rows: list[list]) -> list[Transaction]:
    """Map HDFC's statement layouts onto the canonical schema.

    The Excel export hides the header below preamble rows (customer, branch,
    period) between rows of asterisks, and ends with a STATEMENT SUMMARY
    block of totals. The Delimited export is the same table with every field
    space-padded and 0.00 in the unused amount column. Dates are dd/mm/yy.

    Built from HDFC's known export layouts and synthetic samples; no real
    HDFC statement has been through it yet (unlike SBI's field test).
    """
    from refundradar.formats import _cell_date

    header_idx, cols = next(
        ((idx, c) for idx, c in enumerate(map(_hdfc_columns, rows)) if c),
        (None, None),
    )
    if header_idx is None:
        raise ValueError(
            "Could not find HDFC's transaction table header (Date / Narration "
            "/ Withdrawal Amt. / Deposit Amt. / Closing Balance) in this file."
        )

    txns = []
    for row in rows[header_idx + 1:]:
        if any("statement summary" in str(c).lower() for c in row):
            break  # the totals below would read as a phantom transaction
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
                             balance=_amount(get("balance")), bank="HDFC")
        if t.ref is None:
            t.ref = _hdfc_ref(get("ref"))
        txns.append(t)
    if not txns:
        # A silent empty list would audit as "Rs.0 owed" — say it failed.
        raise ValueError(
            "Found HDFC's transaction table but could not read any rows from "
            "it (expected dd/mm/yy dates and Withdrawal/Deposit amounts). The "
            "export layout may have changed."
        )
    return txns


def _parse_bank_rows(rows: list[list]) -> list[Transaction]:
    """Hand spreadsheet rows to the mapper for the bank layout they carry."""
    if any(_hdfc_columns(row) for row in rows):
        return parse_hdfc_rows(rows)
    return parse_sbi_rows(rows)


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
            return _parse_bank_rows(rows)
    return _parse_bank_rows(load_rows(data, password=password))
