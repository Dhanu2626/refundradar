"""Read a statement export into canonical Transactions.

Supports the generic CSV format used by samples/demo_statement.csv (Date,
Narration,Ref,Debit,Credit,Balance with dd-mm-yyyy dates) plus bank exports:
SBI and HDFC each get a small row mapper. All of them normalize into the same
schema so nothing downstream cares where the data came from. Both bank
mappers read strictly: a row they can't account for stops the audit, naming
the row, and the rows must reproduce the bank's own running balance.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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


NO_BANK_TABLE = ("Could not find an SBI or HDFC transaction table in this file. "
                 "RefundRadar reads SBI and HDFC statement exports, and CSV with the "
                 "columns Date, Narration, Ref, Debit, Credit, Balance.")


def _sbi_columns(row: list) -> dict[str, int] | None:
    """Column indexes if `row` heads a table SBI's way, else None.

    SBI heads the table Txn Date | Value Date | Description | Ref
    No./Cheque No. | Branch Code | Debit | Credit | Balance; the real export
    field-tested on 2026-07-24 said Details for Description. Columns are
    found by header NAME, not position, so layout drift across portal
    versions doesn't break the mapping.
    """
    cols = {}
    for i, cell in enumerate(row):
        n = str(cell).strip().lower() if cell is not None else ""
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
    if {"date", "narration", "debit", "credit", "balance"} <= set(cols):
        return cols
    return None


def _is_sbi(rows: list[list], header_idx: int, cols: dict[str, int]) -> bool:
    """Whether a Date / Debit / Credit table is SBI's and not another bank's:
    SBI names its reference column Ref No./Cheque No., and prints its IFSC
    (SBIN0...) or its name above the table."""
    header = rows[header_idx]
    ref = str(header[cols["ref"]]).lower() if "ref" in cols else ""
    if "ref" in ref and "cheque" in ref:
        return True
    above = " ".join(str(c) for r in rows[:header_idx] for c in r if c is not None).lower()
    return bool(re.search(r"\bsbin0|state bank of india", above))


def parse_sbi_rows(rows: list[list]) -> list[Transaction]:
    """Map SBI's spreadsheet layout onto the canonical schema.

    SBI statements carry preamble rows (account holder, branch, period)
    before the header, and a line of text after the table. Inside the table
    the only rows passed over are blank rows, a repeated header, lines of
    text with no amount (a note, a wrapped description, the footer), and
    dated rows that move no money. Any other row stops the audit, naming the
    row, the column and the cell: an amount on a row without a readable
    date, an amount or Balance that isn't a plain number, both amounts
    filled. The rows must reproduce SBI's own Balance column (DECISIONS.md,
    D16). A silently dropped row could be the very refund being audited.
    """
    from refundradar.formats import _cell_date

    header_idx, cols = next(
        ((idx, c) for idx, c in enumerate(map(_sbi_columns, rows)) if c),
        (None, None),
    )
    if header_idx is None:
        raise ValueError(NO_BANK_TABLE)
    header = rows[header_idx]
    name = lambda key: _column_name(header, cols[key])
    if not _is_sbi(rows, header_idx, cols):
        raise ValueError(
            f"This statement's table ({name('date')} / {name('narration')} / "
            f"{name('debit')} / {name('credit')}) is not laid out the way SBI or HDFC "
            "exports are. RefundRadar reads SBI and HDFC statements; other banks "
            "aren't supported yet."
        )

    txns = []
    ledger = []  # (row number, balance change, printed Balance)
    for idx in range(header_idx + 1, len(rows)):
        row, row_no = rows[idx], idx + 1
        cells = ["" if c is None else str(c).strip() for c in row]
        if not any(ch.isalnum() for c in cells for ch in c) or _sbi_columns(row):
            continue  # blank row, separator, or the header repeated
        get = lambda key: row[cols[key]] if cols[key] < len(row) else None
        date_text = "" if get("date") is None else str(get("date")).strip()
        txn_date = _cell_date(get("date")) if date_text else None
        if txn_date is None:
            if all(str(get(k) or "").strip() in ("", "-") for k in ("debit", "credit")):
                continue  # a line of text: a note, a wrapped description, the footer
            raise ValueError(
                f"Row {row_no}, {name('date')}: expected a date, found "
                f"{date_text!r} on a row with an amount. Stopping rather than "
                "skipping a row that could be a payment or its refund."
            )
        debit = _number(get("debit"), row_no, name("debit")) or None
        credit = _number(get("credit"), row_no, name("credit")) or None
        if debit is not None and credit is not None:
            raise ValueError(
                f"Row {row_no}: both {name('debit')} ({debit}) and "
                f"{name('credit')} ({credit}) are filled, so the direction of "
                "the money is unclear."
            )
        balance = _number(get("balance"), row_no, name("balance"), signed=True)
        if debit is None and credit is None:
            ledger.append((row_no, Decimal(0), balance))
            continue  # a dated line that moved no money, such as an opening balance
        narration = str(get("narration") or "").strip()
        t = make_transaction(txn_date, debit or credit, debit is not None,
                             narration, balance=balance, bank="SBI")
        ref_cell = str(get("ref") or "").strip() if "ref" in cols else ""
        if ref_cell and ref_cell.upper() not in ("", "-", "NONE", "TRANSFER TO", "TRANSFER FROM"):
            if t.ref is None:
                t.ref = ref_cell
        txns.append(t)
        ledger.append((row_no, -t.amount if t.is_debit else t.amount, balance))
    if not txns:
        raise ValueError(
            "Found SBI's transaction table but no transactions in it. The "
            "export layout may have changed."
        )
    _check_balances(txns, ledger, name("balance"))
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

    HDFC left-pads a 12-digit UPI/IMPS RRN with zeros (0000603412345678);
    unpadding lines it up with the same RRN quoted in another row's
    narration. The padding width is inferred, not confirmed, so any run of
    zeros ahead of the last 12 digits is stripped. An all-zero cell means
    the row has no reference.
    """
    ref = str(cell or "").strip()
    if not ref.strip("0"):
        return None
    m = re.fullmatch(r"0+(\d{12})", ref)
    return m.group(1) if m else ref


def _set_hdfc_refs(t: Transaction, col_ref: str | None) -> None:
    """Keep every reference an HDFC row prints, so either can match its pair.

    make_transaction took t.ref from the narration. When Chq./Ref.No. says
    something else, nothing on the statement tells which one a later
    reversal will quote, so both become match keys. The column also takes
    the display slot from a 16-character token guessed out of narration
    text, but never from a 12-digit RRN.
    """
    if col_ref is None or col_ref == t.ref:
        return
    if t.ref is None or not t.ref.isdigit():
        t.ref, col_ref = col_ref, t.ref
    t.alt_ref = col_ref


def _number(cell, row_no: int, column: str, *, signed: bool = False) -> Decimal | None:
    """A numeric statement cell: None when blank, else a Decimal; anything else raises.

    Strict on purpose: text such as "450.00 Cr" raises rather
    than reading as blank, because a row read as blank is a dropped row, and
    the dropped row could be the refund. Amounts must be positive; a Closing
    Balance may be negative (an overdraft).
    """
    text = "" if cell is None else str(cell).replace(",", "").replace("₹", "").strip()
    if text in ("", "-"):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or (value < 0 and not signed):
        kind = "a plain number" if signed else "a plain positive number"
        raise ValueError(f"Row {row_no}, {column}: {str(cell).strip()!r} is not {kind}.")
    # a spreadsheet number cell arrives as a float (2000.0): state it in paise,
    # but never round a value that carries more decimals than that
    paise = Decimal(f"{value:.2f}")
    return paise if paise == value else value


def _balance_break(ledger) -> tuple[int, int, Decimal, Decimal] | None:
    """(row, previous balance row, expected, printed) for the first printed
    balance the rows before it don't reproduce, or None if all add up."""
    prev, prev_row, moved = None, None, Decimal(0)
    for row_no, change, printed in ledger:
        moved += change
        if printed is None:
            continue
        if prev is not None and prev + moved != printed:
            return row_no, prev_row, prev + moved, printed
        prev, prev_row, moved = printed, row_no, Decimal(0)
    return None


def _check_balances(txns: list[Transaction], ledger, column: str) -> None:
    """Stop unless the rows reproduce the bank's own running balance.

    Walks the rows oldest-first. Only the dates may say an export runs
    newest-first: accepting whichever direction adds up would let a short
    statement pass by coincidence.
    """
    dates = [t.txn_date for t in txns]
    newest_first = dates != sorted(dates) and dates == sorted(dates, reverse=True)
    broken = _balance_break(ledger[::-1] if newest_first else ledger)
    if broken is not None:
        row_no, prev_row, expected, printed = broken
        raise ValueError(
            f"Row {row_no}, {column}: the statement says {printed:,.2f}, "
            f"but row {prev_row}'s balance and the rows between lead to "
            f"{expected:,.2f}, so a row is missing, duplicated or misread. "
            "Stopping rather than auditing a statement that doesn't add up."
        )


def _column_name(header: list, i: int) -> str:
    name = str(header[i]).strip() if i < len(header) and header[i] is not None else ""
    return name or f"column {i + 1}"


def _rejoin_narration(row: list, width: int, narration: int) -> list:
    """A row of the Delimited download with its narration back in one piece.

    That export separates fields with commas and, as far as is known, doesn't
    quote them, so a narration such as HDFC's NEFT "...-NETBANK, MUM-..." comes
    out as two fields and pushes every later column one place right. The
    narration is the only free-text column, so the surplus cells are its own;
    the dates, amounts and running balance are still checked after.
    """
    surplus = len(row) - width
    while surplus > 0 and str(row[-1] if row[-1] is not None else "").strip() == "":
        row, surplus = row[:-1], surplus - 1  # trailing empty cells aren't text
    if surplus <= 0:
        return row
    text = ",".join(str(c) for c in row[narration:narration + surplus + 1])
    return row[:narration] + [text] + row[narration + surplus + 1:]


def _refuse_rows_after_summary(rows: list[list], cols: dict, summary_idx: int) -> None:
    """Nothing but totals may follow the summary: a second statement or
    transactions pasted below it would otherwise never be read."""
    from refundradar.formats import _cell_date

    for idx in range(summary_idx + 1, len(rows)):
        row = rows[idx]
        cell = lambda key: row[cols[key]] if cols[key] < len(row) else None
        if _hdfc_columns(row):
            found = "another statement's header"
        elif (isinstance(cell("date"), (str, date))  # numbers here are totals
              and _cell_date(cell("date"))
              and any(str(cell(k) or "").strip() not in ("", "-") for k in ("debit", "credit"))):
            found = "a dated row with an amount"
        else:
            continue
        raise ValueError(
            f"Row {idx + 1}: {found} after the statement summary on row "
            f"{summary_idx + 1}. Audit each HDFC export on its own."
        )


def parse_hdfc_rows(rows: list[list]) -> list[Transaction]:
    """Map HDFC's statement layouts onto the canonical schema.

    The Excel export hides the header below preamble rows (customer, branch,
    period) between rows of asterisks, and ends with a STATEMENT SUMMARY
    block of totals. The Delimited export is the same table with every field
    space-padded and 0.00 in the unused amount column. Dates are dd/mm/yy.

    No real HDFC statement has been through this yet (DECISIONS.md, D10), so
    it reads strictly: a row it can't account for stops the audit, naming
    the row, column and cell, instead of being skipped, and the rows must
    reproduce HDFC's own Closing Balance column. A silently dropped row
    could be the very refund being audited.
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
    header = rows[header_idx]
    name = lambda key: _column_name(header, cols[key])

    txns = []
    ledger = []  # (row number, balance change, printed Closing Balance)
    for idx in range(header_idx + 1, len(rows)):
        row, row_no = _rejoin_narration(rows[idx], len(header), cols["narration"]), idx + 1
        cells = ["" if c is None else str(c).strip() for c in row]
        if any("statement summary" in c.lower() for c in cells):
            _refuse_rows_after_summary(rows, cols, idx)
            break  # the totals below would read as a phantom transaction
        if not any(ch.isalnum() for c in cells for ch in c) or _hdfc_columns(row):
            continue  # blank row, asterisk separator, or the header repeated
        get = lambda key: row[cols[key]] if key in cols and cols[key] < len(row) else None
        date_text = "" if get("date") is None else str(get("date")).strip()
        txn_date = _cell_date(get("date")) if date_text else None
        if txn_date is None:
            raise ValueError(
                f"Row {row_no}, {name('date')}: expected a dd/mm/yy date, found "
                f"{date_text!r}. Stopping rather than skipping a row that could "
                "be a payment or its refund."
            )
        debit = _number(get("debit"), row_no, name("debit")) or None
        credit = _number(get("credit"), row_no, name("credit")) or None
        if debit is not None and credit is not None:
            raise ValueError(
                f"Row {row_no}: both {name('debit')} ({debit}) and "
                f"{name('credit')} ({credit}) are filled, so the direction of "
                "the money is unclear."
            )
        balance = _number(get("balance"), row_no, name("balance"), signed=True)
        if debit is None and credit is None:
            # A dated line that moved no money, such as an opening balance, is
            # only safe to pass over if no other column holds a stray amount.
            for i, text in enumerate(cells):
                other = _cell_date(row[i]) if text and i not in cols.values() else None
                if text and i not in cols.values() and (
                        other is None or abs((other - txn_date).days) > 31):
                    raise ValueError(
                        f"Row {row_no}, {_column_name(header, i)}: found {text!r} "
                        f"on a row with no {name('debit')} or {name('credit')}; "
                        "it may be an amount in the wrong column."
                    )
            ledger.append((row_no, Decimal(0), balance))
            continue
        narration = str(get("narration") or "").strip()
        t = make_transaction(txn_date, debit or credit, debit is not None,
                             narration, balance=balance, bank="HDFC")
        _set_hdfc_refs(t, _hdfc_ref(get("ref")))
        txns.append(t)
        ledger.append((row_no, -t.amount if t.is_debit else t.amount, balance))
    if not txns:
        raise ValueError(
            "Found HDFC's transaction table but no transactions in it. The "
            "export layout may have changed."
        )
    _check_balances(txns, ledger, name("balance"))
    return txns


def _parse_bank_rows(rows: list[list]) -> list[Transaction]:
    """Hand spreadsheet rows to the mapper for the bank layout they carry."""
    if any(_hdfc_columns(row) for row in rows):
        return parse_hdfc_rows(rows)
    return parse_sbi_rows(rows)


def parse_rows(rows: list[list]) -> list[Transaction]:
    """Read a statement's rows. Rows rebuilt from a PDF have no row numbers
    to show, so a refusal names the page and row instead ("Page 2, row 7")."""
    try:
        return _parse_bank_rows(rows)
    except ValueError as e:
        if not hasattr(rows, "explain"):
            raise
        raise ValueError(rows.explain(str(e))) from None


def parse_statement_file(
    path: str | Path, password: str | None = None
) -> list[Transaction]:
    """Open any supported statement file: CSV, xlsx, xls, PDF, or encrypted."""
    return parse_statement_bytes(Path(path).read_bytes(), password=password)


def parse_statement_bytes(
    data: bytes, password: str | None = None
) -> list[Transaction]:
    """Read a statement from its raw bytes, in memory; see parse_statement_file."""
    from refundradar.formats import load_rows, sniff

    if sniff(data) == "text":
        text = data.decode("utf-8-sig", errors="replace")
        try:
            return parse_generic_csv_text(text)
        except ValueError:
            rows = list(csv.reader(io.StringIO(text)))
            return _parse_bank_rows(rows)
    return parse_rows(load_rows(data, password=password))
