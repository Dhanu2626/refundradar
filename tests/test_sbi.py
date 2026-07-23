"""SBI layout mapping and file-format sniffing (synthetic data only)."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from refundradar.formats import OLE_MAGIC, ZIP_MAGIC, sniff
from refundradar.parser import parse_sbi_rows

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
    with pytest.raises(ValueError, match="transaction table header"):
        parse_sbi_rows([["just"], ["noise"]])


def test_sniff_magic_bytes():
    assert sniff(ZIP_MAGIC + b"rest") == "xlsx"
    assert sniff(b"Date,Narration\n1,2") == "text"
    assert sniff(b"  <html><table>") == "html"


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
