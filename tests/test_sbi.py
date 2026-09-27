"""SBI layout mapping and file-format sniffing (synthetic data only)."""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from refundradar.audit import build_audit
from refundradar.formats import OLE_MAGIC, ZIP_MAGIC, sniff
from refundradar.parser import parse_sbi_rows, parse_statement_file
from refundradar.reconcile import CONFIRM, ON_TIME

ROOT = Path(__file__).resolve().parent.parent
SBI_SAMPLE = ROOT / "samples" / "sbi_statement.xlsx"
SBI_AS_OF = date(2026, 9, 1)

SBI_ROWS = [
    ["Account Name", ":", "MR TEST CUSTOMER"],
    ["Address", ":", "HYDERABAD"],
    ["Account Statement from 1 Jan 2026 to 30 Jun 2026"],
    [],
    ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.",
     "Branch Code", "Debit", "Credit", "Balance"],
    [datetime(2026, 2, 3), datetime(2026, 2, 3),
     "TO TRANSFER-UPI/DR/504212345678/SWIGGY.ORDER@ICICI/PAY", "504212345678",
     "1234", "450.00", None, "39,550.00"],
    ["4 Feb 2026", "4 Feb 2026",
     "BY TRANSFER-UPI/CR/504212345678/REVERSAL OF FAILED TXN", "504212345678",
     "1234", None, "450.00", "40,000.00"],
    [datetime(2026, 3, 1), datetime(2026, 3, 1),
     "NWD-459912XX3456-SBI ATM SECUNDERABAD", "S1CN998877", "1234",
     "5,000.00", None, "35,000.00"],
    ["", "", "** This is a computer generated statement **", "", "", "", "", ""],
]


def test_header_found_despite_preamble():
    txns = parse_sbi_rows(SBI_ROWS)
    assert len(txns) == 3


def test_text_and_datetime_dates_both_parse():
    txns = parse_sbi_rows(SBI_ROWS)
    assert txns[0].txn_date == date(2026, 2, 3)
    assert txns[1].txn_date == date(2026, 2, 4)


def test_comma_amounts_and_direction():
    txns = parse_sbi_rows(SBI_ROWS)
    assert txns[2].amount == Decimal("5000.00")
    assert txns[2].is_debit is True
    assert txns[1].is_debit is False


def test_ref_and_channel_detected():
    txns = parse_sbi_rows(SBI_ROWS)
    assert txns[0].ref == "504212345678"
    assert txns[0].channel == "upi_p2m"
    assert txns[2].channel == "atm"
    assert txns[0].bank == "SBI"


def test_missing_header_raises_clear_error():
    with pytest.raises(ValueError, match="SBI or HDFC transaction table"):
        parse_sbi_rows([["just"], ["noise"]])


def test_sniff_magic_bytes():
    assert sniff(ZIP_MAGIC + b"rest") == "xlsx"
    assert sniff(b"Date,Narration\n1,2") == "text"
    assert sniff(b"  <html><table>") == "html"


def _sbi_txn(day, amount, is_debit, narration, ref):
    from refundradar.model import make_transaction
    return make_transaction(date(2026, 6, day), amount, is_debit, narration,
                            bank="SBI")


def test_fresh_ref_reversal_on_time_is_matched():
    from refundradar.reconcile import ON_TIME, reconcile
    txns = [
        _sbi_txn(10, "500.00", True,
                 "WDL TFR UPI/DR/616128000001/LENSKART/Payment", "x"),
        _sbi_txn(10, "500.00", False,
                 "DEP TFR UPI/REF/616903000009/CR", "y"),  # same day, fresh ref
    ]
    incs = reconcile(txns)
    assert len(incs) == 1
    assert incs[0].status == ON_TIME  # on time -> Rs.0, no user action


def test_fresh_ref_reversal_late_needs_confirmation_not_autoclaim():
    from refundradar.reconcile import CONFIRM, reconcile
    txns = [
        _sbi_txn(1, "500.00", True,
                 "WDL TFR UPI/DR/616128000002/PAYTMQR9@PAYTM/Pay", "x"),
        _sbi_txn(9, "500.00", False,
                 "DEP TFR UPI/REF/616903000010/CR", "y"),  # 8 days later, p2m T+5
    ]
    incs = reconcile(txns)
    assert len(incs) == 1
    assert incs[0].status == CONFIRM  # inferred link -> never an auto-claim


def test_ordinary_same_amount_roundtrip_is_not_flagged():
    from refundradar.reconcile import reconcile
    txns = [
        _sbi_txn(1, "500.00", True,
                 "WDL TFR UPI/DR/616128000003/J JYOSHNA/Pay", "x"),
        _sbi_txn(3, "500.00", False,
                 "DEP TFR UPI/CR/616903000011/J JYOSHNA", "y"),  # normal incoming
    ]
    assert reconcile(txns) == []  # a coincidental round-trip, not a reversal


def test_reversal_outside_window_is_not_matched():
    from refundradar.reconcile import CONFIRM, reconcile
    txns = [
        _sbi_txn(1, "500.00", True,
                 "WDL TFR UPI/DR/616128000004/LENSKART/Pay", "x"),
        _sbi_txn(20, "500.00", False,
                 "DEP TFR UPI/REF/616903000012/CR", "y"),  # 19 days > window
    ]
    # Not matched: nothing is claimed. Since D12 the only possible pairing is
    # asked about instead of dropped, because it may be a late refund.
    [inc] = reconcile(txns)
    assert (inc.status, inc.ruling) == (CONFIRM, None)


def test_sbi_csv_export_routes_to_sbi_mapper(tmp_path):
    from refundradar.parser import parse_statement_file
    csv_text = (
        "Account Name,:,MR TEST\n"
        "Txn Date,Value Date,Description,Ref No./Cheque No.,Branch Code,Debit,Credit,Balance\n"
        '3 Feb 2026,3 Feb 2026,TO TRANSFER-UPI/DR/504212345678/SWIGGY.ORDER@ICICI/PAY,504212345678,1234,450.00,,"39,550.00"\n'
        '4 Feb 2026,4 Feb 2026,BY TRANSFER-UPI/CR/504212345678/REVERSAL OF FAILED TXN,504212345678,1234,,450.00,"40,000.00"\n'
    )
    f = tmp_path / "sbi.csv"
    f.write_text(csv_text, encoding="utf-8")
    txns = parse_statement_file(f)
    assert len(txns) == 2
    assert txns[0].channel == "upi_p2m"
    assert txns[0].bank == "SBI"


# --- Rows the SBI reader must never drop or misread silently (D16) ----------
# The reader used to pass over any row whose date or amount it couldn't read,
# so the web app refused SBI files: a dropped row could be the refund.

SBI_HEADER = SBI_ROWS[4]


def _sbi(day, narration, ref="-", debit="", credit="", balance=""):
    return [day, day, narration, ref, "1234", debit, credit, balance]


PAY = _sbi("3 Feb 2026", "WDL TFR UPI/DR/603412345678/SWIGGY/Payment", debit="450.00",
           balance="39,550.00")
BACK = _sbi("5 Feb 2026", "DEP TFR UPI/REF/603499990001/CR", credit="450.00",
            balance="40,000.00")


def _sbi_table(*rows):
    return [["IFS Code", ":", "SBIN0XXXXXX"], SBI_HEADER, *rows]  # PAY is row 3


@pytest.mark.parametrize("row, where, cell", [
    (_sbi("5 Feb 2026", BACK[2], credit="(450.00)", balance="40,000.00"), "Credit", "'(450.00)'"),
    (_sbi("5 Feb 2026", BACK[2], debit="450.00 Dr", balance="39,100.00"), "Debit", "'450.00 Dr'"),
    (_sbi("5 Feb 2026", BACK[2], credit="450.00", balance="40,000.00 Cr"),
     "Balance", "'40,000.00 Cr'"),
    (_sbi("Feb 5th", BACK[2], credit="450.00", balance="40,000.00"), "Txn Date", "'Feb 5th'"),
    (["", "", "DEP TFR UPI/REF/603499990001/CR", "", "", "", "450.00", "40,000.00"],
     "Txn Date", "''"),
], ids=["bracketed amount", "Dr on amount", "Cr on balance", "unreadable date",
        "amount without a date"])
def test_refusal_names_row_column_and_cell(row, where, cell):
    with pytest.raises(ValueError) as err:
        parse_sbi_rows(_sbi_table(PAY, row))
    assert str(err.value).startswith(f"Row 4, {where}:")
    assert cell in str(err.value)


def test_both_amounts_filled_is_refused():
    row = _sbi("5 Feb 2026", BACK[2], debit="450.00", credit="450.00", balance="39,550.00")
    with pytest.raises(ValueError, match=r"^Row 4: both Debit \(450.00\) and Credit"):
        parse_sbi_rows(_sbi_table(PAY, row))


def test_rows_must_reproduce_sbis_balance():
    skipped = _sbi("5 Feb 2026", BACK[2], credit="450.00", balance="40,100.00")
    with pytest.raises(ValueError, match="Row 4, Balance: the statement says 40,100.00, but row 3's balance "
                                         "and the rows between lead to 40,000.00"):
        parse_sbi_rows(_sbi_table(PAY, skipped))


def test_text_lines_blank_rows_and_a_repeated_header_are_passed_over():
    wrapped = ["", "", "SWIGGY ORDER 8812 (CONTD)", "", "", "", "", ""]
    footer = ["**This is a computer generated statement and does not require a signature."]
    txns = parse_sbi_rows(_sbi_table(PAY, [], ["", None, " "], SBI_HEADER, wrapped, BACK, footer))
    assert [(t.amount, t.is_debit) for t in txns] == [(Decimal("450.00"), True),
                                                      (Decimal("450.00"), False)]


def test_dated_row_without_money_is_passed_over_but_balance_checked():
    opening = _sbi("1 Feb 2026", "BALANCE B/F", balance="40,000.00")
    assert len(parse_sbi_rows(_sbi_table(opening, PAY))) == 1
    wrong = _sbi("1 Feb 2026", "BALANCE B/F", balance="41,000.00")
    with pytest.raises(ValueError, match="Row 4, Balance: .*row 3's balance"):
        parse_sbi_rows(_sbi_table(wrong, PAY))


def test_newest_first_export_balances_read_bottom_up():
    assert len(parse_sbi_rows(_sbi_table(BACK, PAY))) == 2


def test_the_field_tested_header_names_still_read():
    # the real export (2026-07-24) said Details, not Description; a Date column
    # without "Txn" is mapped the same way
    header = ["Date", "Details", "Ref No./Cheque No.", "Debit", "Credit", "Balance"]
    rows = [header, ["3 Feb 2026", PAY[2], "-", "450.00", "", "39,550.00"]]
    [t] = parse_sbi_rows(rows)
    assert (t.bank, t.ref, t.channel) == ("SBI", "603412345678", "upi_p2m")


def test_another_banks_table_is_not_read_as_sbi():
    header = ["Date", "Particulars", "Chq No", "Debit", "Credit", "Balance"]
    rows = [["Account Statement"], header, ["3 Feb 2026", PAY[2], "", "450.00", "", "39,550.00"]]
    with pytest.raises(ValueError, match="not laid out the way SBI or HDFC exports are"):
        parse_sbi_rows(rows)
    # SBI's IFSC above the table says whose statement it is
    assert len(parse_sbi_rows([["IFS Code", ":", "SBIN0XXXXXX"], *rows])) == 1


def test_a_table_with_no_transactions_fails_loudly():
    with pytest.raises(ValueError, match="no transactions in it"):
        parse_sbi_rows(_sbi_table(["**This is a computer generated statement**"]))


# --- The synthetic SBI sample (samples/sbi_statement.xlsx) -------------------

def test_sample_is_what_its_generator_writes():
    sys.path.insert(0, str(ROOT / "tools"))
    import make_sbi_sample
    ws = openpyxl.load_workbook(SBI_SAMPLE, read_only=True).active
    def cells(row):  # as written, without the empty cells a sheet pads rows with
        row = ["" if c is None else c for c in row]
        while row and row[-1] == "":
            row.pop()
        return row
    written = [cells(r) for r in ws.iter_rows(values_only=True)]
    assert [r for r in written if r] == [cells(r) for r in make_sbi_sample.rows() if r]


def test_sample_is_read_in_full_as_sbi():
    txns = parse_statement_file(SBI_SAMPLE)
    assert (len(txns), sum(t.is_debit for t in txns)) == (20, 11)
    assert {t.bank for t in txns} == {"SBI"}


def test_sample_planted_cases_and_nothing_claimed_unasked():
    a = build_audit(parse_statement_file(SBI_SAMPLE), set(), as_of=SBI_AS_OF)
    found = {(i.txn.txn_date.isoformat(), str(i.txn.amount)): i.status for i in a.incidents}
    assert found == {("2026-06-03", "450.00"): ON_TIME, ("2026-06-08", "2000.00"): CONFIRM,
                     ("2026-07-06", "350.00"): ON_TIME, ("2026-07-02", "1299.00"): CONFIRM}
    assert a.total_owed_inr == 0  # a refund that looks late is asked about, not claimed


# --- SBI's password-protected download (formats.py) --------------------------

def _locked_sample(tmp_path, password="Sample@2626"):
    import io
    from msoffcrypto.format.ooxml import OOXMLFile
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(SBI_SAMPLE.read_bytes())).encrypt(password, out)
    path = tmp_path / "sbi_statement.xlsx"
    path.write_bytes(out.getvalue())
    return path


def test_locked_download_is_recognised_and_opens_only_with_its_password(tmp_path):
    from refundradar.formats import EncryptedStatement, WrongPassword
    locked = _locked_sample(tmp_path)
    assert sniff(locked.read_bytes()) == "encrypted"
    with pytest.raises(EncryptedStatement, match="password-protected"):
        parse_statement_file(locked)
    with pytest.raises(WrongPassword, match="doesn't open this statement"):
        parse_statement_file(locked, password="not it")
    assert len(parse_statement_file(locked, password="Sample@2626")) == 20


def test_cli_says_a_wrong_password_is_wrong(tmp_path, capsys):
    from refundradar.__main__ import main
    locked = str(_locked_sample(tmp_path))
    assert main(["audit", locked, "--password", "not it"]) == 1
    assert "That password doesn't open this statement." in capsys.readouterr().out
    assert main(["audit", locked, "--password", "Sample@2626"]) == 0
    assert "20 lines" in capsys.readouterr().out


def test_a_pdf_is_named_as_a_pdf():
    from refundradar.parser import parse_statement_bytes
    assert sniff(b"%PDF-1.7\n") == "pdf"
    with pytest.raises(ValueError, match="^This is a PDF"):
        parse_statement_bytes(b"%PDF-1.7\n1 0 obj\n")
