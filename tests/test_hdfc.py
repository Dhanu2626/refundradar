"""HDFC layout mapping and export routing (synthetic data only)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from refundradar.parser import _hdfc_ref, parse_hdfc_rows, parse_statement_file
from refundradar.reconcile import CONFIRM, LATE, reconcile

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "hdfc_statement.csv"

STARS = ["****************"] * 7
HEADER = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.",
          "Deposit Amt.", "Closing Balance"]
HDFC_ROWS = [
    ["SYNTHETIC SAMPLE - NOT A REAL BANK STATEMENT"],
    ["MR TEST CUSTOMER", "", "", "", "Account No :", "XXXXXXXX1234"],
    ["", "", "", "", "A/C Open Date :", "01/01/20"],
    ["Statement From :", "01/02/2026", "To :", "31/03/2026"],
    STARS,
    HEADER,
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


def test_table_without_transactions_fails_loudly_not_as_empty_statement():
    with pytest.raises(ValueError, match="no transactions"):
        parse_hdfc_rows(HDFC_ROWS[:7] + [STARS])


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


# --- Rows the parser must never drop or misread silently ---------------------

def _row(day, narration, ref="", withdrawal="", deposit="", balance=""):
    return [day, narration, ref, day, withdrawal, deposit, balance]


def _table(*rows):
    return [HEADER, *rows]


PAYMENT = _row("03/02/26", "UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-PAY",
               "0000603412345678", withdrawal="450.00", balance="39,550.00")
REVERSAL = _row("05/02/26", "UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-REVERSAL",
                "0000603412345678", deposit="450.00", balance="40,000.00")


@pytest.mark.parametrize("row, problem", [
    (_row("05-02-26", REVERSAL[1], deposit="450.00"), "no dd/mm/yy date"),
    (_row("05/02/26 10:15", REVERSAL[1], deposit="450.00"), "no dd/mm/yy date"),
    (_row("", REVERSAL[1], deposit="450.00"), "no dd/mm/yy date"),
    (_row("05/02/26", REVERSAL[1], deposit="450.00 Cr"), "not a plain positive number"),
    (_row("05/02/26", REVERSAL[1], deposit="(450.00)"), "not a plain positive number"),
    (_row("05/02/26", REVERSAL[1], withdrawal="-450.00"), "not a plain positive number"),
    (_row("05/02/26", REVERSAL[1], withdrawal="10.00", deposit="450.00"), "both a withdrawal and a deposit"),
    (["", "NARRATION WRAPPED ONTO A SECOND LINE", "", "", "", "", ""], "no dd/mm/yy date"),
], ids=["dd-mm-yy", "date+time", "blank date", "Cr suffix", "brackets", "negative",
        "both amounts", "continuation line"])
def test_unreadable_row_stops_the_audit_instead_of_vanishing(row, problem):
    # each of these rows used to be skipped or misread without a word
    with pytest.raises(ValueError, match=f"Row 3: .*{problem}"):
        parse_hdfc_rows(_table(PAYMENT, row))


def test_blank_separator_and_repeated_header_rows_are_skipped():
    txns = parse_hdfc_rows(_table(PAYMENT, [], ["", None, " "], STARS, HEADER, REVERSAL))
    assert len(txns) == 2


def test_money_in_an_unmapped_column_is_caught_by_the_running_balance():
    moved = _row("05/02/26", REVERSAL[1], "0000603412345678", balance="40,000.00")
    moved[3] = "450.00"  # the amount landed in Value Dt; Closing Balance still rose
    with pytest.raises(ValueError, match="Row 3: the Closing Balance"):
        parse_hdfc_rows(_table(PAYMENT, moved))


def test_duplicated_row_is_caught_by_the_running_balance():
    with pytest.raises(ValueError, match="Row 3: the Closing Balance"):
        parse_hdfc_rows(_table(PAYMENT, PAYMENT))


def test_dated_row_without_money_is_skipped_but_still_balance_checked():
    opening = _row("01/02/26", "OPENING BALANCE", balance="40,000.00")
    assert len(parse_hdfc_rows(_table(opening, PAYMENT))) == 1
    wrong = _row("01/02/26", "OPENING BALANCE", balance="41,000.00")
    with pytest.raises(ValueError, match="Row 3: the Closing Balance"):
        parse_hdfc_rows(_table(wrong, PAYMENT))


def test_newest_first_export_balances_read_bottom_up():
    assert len(parse_hdfc_rows(_table(REVERSAL, PAYMENT))) == 2


def test_totals_without_their_label_still_never_become_a_transaction():
    labels = ["Opening Balance", "", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"]
    totals = [40000.0, "", 1, 0, 450.0, 0.0, 39550.0]  # 40000.0 = Excel serial 6 Jul 2009
    with pytest.raises(ValueError, match="Row 3: .*no dd/mm/yy date"):
        parse_hdfc_rows(_table(PAYMENT, labels, totals))
    with pytest.raises(ValueError, match="the Closing Balance"):
        parse_hdfc_rows(_table(PAYMENT, totals))


def test_a_second_statement_after_the_summary_is_refused():
    rows = _table(PAYMENT, ["STATEMENT SUMMARY  :-"], HEADER, REVERSAL)
    with pytest.raises(ValueError, match="another statement"):
        parse_hdfc_rows(rows)


# --- References: where the original payment's reference may reappear --------

@pytest.mark.parametrize("cell, ref", [
    ("0000603412345678", "603412345678"),        # the inferred 16-digit padding
    ("00603412345678", "603412345678"),          # other widths unpad the same way
    ("000000000603412345678", "603412345678"),
    ("012345678901", "012345678901"),            # an RRN's own leading zero survives
    ("0000012345678901", "012345678901"),
    ("0000000000000000", None),
    ("", None),
    ("CITIN26020112345", "CITIN26020112345"),
])
def test_ref_column_is_unpadded_to_the_rrn(cell, ref):
    assert _hdfc_ref(cell) == ref


LATE_DEBIT = _row("10/02/26", "UPI-PAYTM-PAYTMQR1@PAYTM-PYTM0123456-604112345678-GROCERIES",
                  "0000604112345678", withdrawal="2,000.00", balance="10,000.00")


@pytest.mark.parametrize("narration, ref_cell", [
    ("UPI-PAYTM-PAYTMQR1@PAYTM-PYTM0123456-604112345678-REVERSAL", "0000604112345678"),
    ("REVERSAL-UPI-PAYTM-GROCERIES", "0000604112345678"),
    ("UPI-PAYTM-PAYTMQR1@PAYTM-PYTM0123456-604112345678-REVERSAL", "0000605399998888"),
    ("REVERSAL-UPI-605399998888-GROCERIES", "0000604112345678"),
    ("REVERSAL-UPI-PAYTMQR28100505X-GROCERIES", "0000604112345678"),
    ("REVERSAL-UPI-PAYTM-GROCERIES", "00604112345678"),
], ids=["narration and column", "column only", "narration only",
        "fresh number in narration", "16-char token in narration", "other padding"])
def test_late_refund_is_found_wherever_the_original_reference_appears(narration, ref_cell):
    # 13 days later: past the T+5 deadline AND the 10-day amount+timing
    # window, so only the reference relationship can find it
    reversal = _row("23/02/26", narration, ref_cell, deposit="2,000.00", balance="12,000.00")
    [inc] = reconcile(parse_hdfc_rows(_table(LATE_DEBIT, reversal)), as_of=date(2026, 4, 30))
    assert inc.status == LATE
    assert inc.ruling.compensation_inr == 800
    assert inc.txn.ref == "604112345678"  # the letter cites the payment's own RRN


def _fresh_ref_reversal(day):
    return _row(day, "REVERSAL-UPI-605399998888-GROCERIES", "0000605399998888",
                deposit="2,000.00", balance="12,000.00")


def test_fresh_reference_reversal_in_window_is_asked_not_claimed():
    [inc] = reconcile(parse_hdfc_rows(_table(LATE_DEBIT, _fresh_ref_reversal("19/02/26"))),
                      as_of=date(2026, 4, 30))
    assert inc.status == CONFIRM  # linked by amount+timing only (D9)


def test_fresh_reference_reversal_beyond_window_cannot_be_linked_from_the_statement():
    # Known gap, pinned on purpose: nothing ties these rows together (D9).
    txns = parse_hdfc_rows(_table(LATE_DEBIT, _fresh_ref_reversal("23/02/26")))
    assert reconcile(txns, as_of=date(2026, 4, 30)) == []
    # Confirming the payment failed must still not call it never refunded (D12).
    [inc] = reconcile(txns, {"604112345678"}, as_of=date(2026, 4, 30))
    assert inc.status == CONFIRM


def test_unrecognised_reversal_wording_asks_instead_of_claiming_or_dropping():
    reversal = _row("23/02/26", "UPI-PAYTM-PAYTMQR1@PAYTM-PYTM0123456-604112345678-TXN REVERSED",
                    "0000604112345678", deposit="2,000.00", balance="12,000.00")
    [inc] = reconcile(parse_hdfc_rows(_table(LATE_DEBIT, reversal)), as_of=date(2026, 4, 30))
    assert inc.status == CONFIRM


def test_cli_reports_an_unreadable_statement_instead_of_a_total(tmp_path, capsys):
    from refundradar.__main__ import main
    f = tmp_path / "hdfc.csv"
    f.write_text(
        ",".join(HEADER) + "\n"
        '03/02/26,UPI-SWIGGY-603412345678-PAY,0000603412345678,03/02/26,450.00,,"39,550.00"\n'
        '05/02/26,UPI-SWIGGY-603412345678-REVERSAL,0000603412345678,05/02/26,,450.00 Cr,"40,000.00"\n',
        encoding="utf-8")
    assert main(["audit", str(f)]) == 1
    out = capsys.readouterr().out
    assert "Could not audit hdfc.csv: Row 3" in out
    assert "Total owed" not in out
