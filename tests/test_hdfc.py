"""HDFC layout mapping and export routing (synthetic data only)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from refundradar.parser import parse_hdfc_rows, parse_statement_file

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "hdfc_statement.csv"

STARS = ["****************"] * 7
HDFC_ROWS = [
    ["SYNTHETIC SAMPLE - NOT A REAL BANK STATEMENT"],
    ["MR TEST CUSTOMER", "", "", "", "Account No :", "XXXXXXXX1234"],
    ["", "", "", "", "A/C Open Date :", "01/01/20"],
    ["Statement From :", "01/02/2026", "To :", "31/03/2026"],
    STARS,
    ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.",
     "Deposit Amt.", "Closing Balance"],
    STARS,
    ["03/02/26", "UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-PAYMENT",
     "0000603412345678", "03/02/26", "450.00", "", "39,550.00"],
    [datetime(2026, 2, 5), "UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-REVERSAL",
     "0000603412345678", datetime(2026, 2, 5), "", "450.00", "40,000.00"],
    ["02/03/26", "NWD-512967XXXXXX1234-S1CNB123-HYDERABAD", "0000606110004321",
     "02/03/26", "5,000.00", "", "35,000.00"],
    ["18/03/26", "POS 512967XXXXXX1234 DMART HYDERABAD", "0000000000000000",
     "18/03/26", "899.00", "", "34,101.00"],
    STARS,
    ["STATEMENT SUMMARY  :-"],
    ["Opening Balance", "", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"],
    [40000.0, "", 3, 1, 6349.0, 450.0, 34101.0],  # numeric, as a spreadsheet gives it
    ["This is a computer generated statement and does not require signature."],
]


def test_header_found_despite_preamble_and_separators():
    txns = parse_hdfc_rows(HDFC_ROWS)
    assert len(txns) == 4


def test_two_digit_year_and_datetime_dates_both_parse():
    txns = parse_hdfc_rows(HDFC_ROWS)
    assert txns[0].txn_date == date(2026, 2, 3)
    assert txns[1].txn_date == date(2026, 2, 5)


def test_comma_amounts_and_direction():
    txns = parse_hdfc_rows(HDFC_ROWS)
    assert txns[2].amount == Decimal("5000.00")
    assert txns[2].balance == Decimal("35000.00")
    assert txns[2].is_debit is True
    assert txns[1].is_debit is False


def test_ref_and_channel_detected():
    txns = parse_hdfc_rows(HDFC_ROWS)
    assert txns[0].ref == "603412345678"
    assert txns[0].channel == "upi_p2m"
    assert txns[2].channel == "atm"
    assert txns[3].channel == "pos"
    assert txns[0].bank == "HDFC"


def test_padded_ref_column_is_unpadded_and_all_zero_means_none():
    txns = parse_hdfc_rows(HDFC_ROWS)
    assert txns[2].ref == "606110004321"  # NWD narration has no RRN; column does
    assert txns[3].ref is None


def test_statement_summary_is_not_read_as_a_transaction():
    # 40000.0 in the Date column would otherwise parse as Excel serial 6 Jul 2009
    txns = parse_hdfc_rows(HDFC_ROWS)
    assert all(t.txn_date.year == 2026 for t in txns)


def test_missing_header_raises_clear_error():
    with pytest.raises(ValueError, match="transaction table header"):
        parse_hdfc_rows([["just"], ["noise"]])


def test_unreadable_table_fails_loudly_not_as_empty_statement():
    rows = HDFC_ROWS[:7] + [["2026.02.03", "UPI-SWIGGY", "", "", "450.00", "", ""]]
    with pytest.raises(ValueError, match="could not read any rows"):
        parse_hdfc_rows(rows)


def test_delimited_export_routes_to_hdfc_mapper(tmp_path):
    # HDFC's "Delimited" download: space-padded fields, 0.00 in the unused
    # column. Before HDFC support this header reached the SBI mapper, which
    # dropped every dd/mm/yy row and audited an empty statement.
    text = (
        " Date     ,Narration                                                       "
        ",Value Dat,Debit Amount       ,Credit Amount      ,Chq/Ref Number   ,Closing Balance\n"
        " 03/02/26 ,UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-PAYMENT  "
        ",03/02/26 ,           450.00  ,             0.00  ,0000603412345678 ,       39550.00\n"
        " 05/02/26 ,UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-REVERSAL "
        ",05/02/26 ,             0.00  ,           450.00  ,0000603412345678 ,       40000.00\n"
    )
    f = tmp_path / "hdfc.txt"
    f.write_text(text, encoding="utf-8")
    txns = parse_statement_file(f)
    assert [(t.txn_date, t.amount, t.is_debit) for t in txns] == [
        (date(2026, 2, 3), Decimal("450.00"), True),
        (date(2026, 2, 5), Decimal("450.00"), False),
    ]
    assert txns[0].bank == "HDFC"


def test_excel_export_saved_as_csv_routes_to_hdfc_mapper():
    txns = parse_statement_file(SAMPLE)
    assert len(txns) == 22
    assert {t.bank for t in txns} == {"HDFC"}


def test_spreadsheet_export_routes_to_hdfc_mapper(tmp_path):
    # HDFC ships legacy .xls; an .xlsx takes the same load_rows -> mapper
    # route (writing a real .xls would need xlwt, not a dependency).
    import openpyxl
    wb = openpyxl.Workbook()
    for row in HDFC_ROWS:
        wb.active.append(row)
    f = tmp_path / "hdfc.xlsx"
    wb.save(f)
    txns = parse_statement_file(f)
    assert len(txns) == 4
    assert txns[0].bank == "HDFC"


def test_sample_amounts_agree_with_hdfc_running_balance():
    balance = Decimal("40000.00")  # the sample's opening balance
    for t in parse_statement_file(SAMPLE):
        balance += -t.amount if t.is_debit else t.amount
        assert t.balance == balance, t.narration


def test_sample_statement_planted_incidents():
    from refundradar.reconcile import EXCLUDED, LATE, ON_TIME, reconcile
    incs = reconcile(parse_statement_file(SAMPLE), as_of=date(2026, 4, 30))
    by_ref = {i.txn.ref: i for i in incs if i.txn.ref}
    assert by_ref["603412345678"].status == ON_TIME
    # the reversal row carries this RRN only in the zero-padded ref column
    assert by_ref["604112345678"].status == LATE
    assert by_ref["604112345678"].ruling.compensation_inr == 800
    assert by_ref["606110004321"].status == LATE  # ATM cash not dispensed
    assert by_ref["606110004321"].ruling.compensation_inr == 600
    assert by_ref["604712345678"].status == EXCLUDED  # trap: returned order
    pos = next(i for i in incs if i.txn.channel == "pos")
    assert pos.status == ON_TIME  # no reference: matched by amount+timing (D9)
    assert "607912345678" not in by_ref  # never reversed: invisible until confirmed (D6)


def test_sample_confirmed_failure_is_claimed():
    from refundradar.audit import build_audit
    a = build_audit(parse_statement_file(SAMPLE), {"607912345678"},
                    as_of=date(2026, 4, 30))
    # UPI P2P due back by 21 Mar (T+1): 40 days late on 30 Apr
    assert a.total_owed_inr == 800 + 600 + 4000
    assert a.stuck_amount == Decimal("2499.00")
    assert a.on_time_count == 2
