"""Statements laid out the way SBI's and HDFC's downloads are (samples/realistic/,
written by tools/make_realistic_statements.py; synthetic data, real layouts):
every format read completely and identically, and the planted cases found."""

import base64
import csv
import io
import sys
from datetime import date
from pathlib import Path

import openpyxl
import pytest
import xlrd
from fastapi.testclient import TestClient

from refundradar.audit import build_audit
from refundradar.parser import parse_hdfc_rows, parse_statement_file
from refundradar.reconcile import CONFIRM, EXCLUDED, LATE, ON_TIME
from refundradar.webapp import app

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "samples" / "realistic"
sys.path.insert(0, str(ROOT / "tools"))
import make_realistic_statements as mk  # noqa: E402

AS_OF = date(2026, 9, 1)
HDFC = ["hdfc_netbanking.xls", "hdfc_netbanking_saved_as.csv", "hdfc_delimited.txt",
        "hdfc_netbanking.pdf"]
SBI = ["sbi_account_statement.xlsx", "sbi_account_statement_locked.xlsx", "sbi_details_layout.xlsx",
       "sbi_account_statement.pdf", "sbi_account_statement_locked.pdf"]


def read(name):
    return parse_statement_file(REAL / name, password=mk.SBI_PASSWORD if "locked" in name else None)


def _values(rows):
    out = []
    for row in rows:
        row = ["" if c is None else c for c in row]
        while row and row[-1] == "":
            row.pop()
        if row:
            out.append(row)
    return out


def test_the_committed_files_are_what_the_generator_writes():
    # byte for byte: their Windows line endings are part of the layout (.gitattributes keeps them)
    assert (REAL / "hdfc_delimited.txt").read_bytes() == mk.hdfc_delimited().encode("utf-8")
    assert (REAL / "hdfc_netbanking_saved_as.csv").read_bytes() == mk.hdfc_csv().encode("utf-8")
    ws = xlrd.open_workbook(REAL / "hdfc_netbanking.xls").sheet_by_index(0)
    xls = [[ws.cell_value(r, c) for c in range(ws.ncols)] for r in range(ws.nrows)]
    assert _values(xls) == _values(mk.hdfc_sheet())
    for name, yono in (("sbi_account_statement.xlsx", False), ("sbi_details_layout.xlsx", True)):
        sheet = openpyxl.load_workbook(REAL / name, read_only=True).active
        assert _values(sheet.iter_rows(values_only=True)) == _values(mk.sbi_sheet(yono)), name


@pytest.mark.parametrize("names, bank, count", [(HDFC, "HDFC", 40), (SBI, "SBI", 20)])
def test_every_download_of_one_statement_reads_the_same_transactions(names, bank, count):
    key = lambda t: [(x.txn_date, x.amount, x.is_debit, x.narration, x.ref, x.alt_ref, x.channel, x.balance)
                     for x in t]
    first = read(names[0])
    assert (len(first), {x.bank for x in first}) == (count, {bank})
    for name in names[1:]:
        assert key(read(name)) == key(first), name


def test_a_narration_with_a_comma_survives_the_delimited_download():
    # HDFC's NEFT narrations say "NETBANK, MUM"; the Delimited file doesn't quote them
    [neft] = [t for t in read("hdfc_delimited.txt") if t.narration.startswith("NEFT DR")]
    assert neft.narration == "NEFT DR-SBIN0000999-SAMPLE RELATIVE-NETBANK, MUM-N199262615"
    assert (str(neft.amount), neft.channel) == ("10000.00", "neft")


def _delimited_rows(text):
    return list(csv.reader(io.StringIO(text)))


def test_rejoining_never_rescues_a_row_that_still_doesnt_fit():
    lines = mk.hdfc_delimited().splitlines()
    # a comma inside the reference column, not the narration: the columns can't all
    # be made to fit, so the row is still refused, never guessed at
    bad = [line.replace("0000615412345601 ,", "00006154,12345601 ,", 1) if i == 3 else line
           for i, line in enumerate(lines)]
    with pytest.raises(ValueError, match="^Row 4"):
        parse_hdfc_rows(_delimited_rows("\n".join(bad)))
    # trailing empty cells are not narration text: nothing shifts
    padded = [line + ",," if i else line for i, line in enumerate(lines)]
    assert len(parse_hdfc_rows(_delimited_rows("\n".join(padded)))) == 40


def _found(name):
    a = build_audit(read(name), set(), as_of=AS_OF)
    return a, {(i.txn.txn_date.isoformat(), str(i.txn.amount)): i.status for i in a.incidents}


def test_hdfc_planted_cases():
    a, found = _found("hdfc_netbanking.xls")
    assert found == {
        ("2026-06-03", "486.00"): ON_TIME,     # same reference, REVERSAL the next day
        ("2026-06-12", "5000.00"): CONFIRM,    # REV-NWD: a wording the engine doesn't know, so it asks
        ("2026-06-18", "1799.00"): EXCLUDED,   # a returned order's refund, not a failure
        ("2026-07-06", "3245.00"): LATE,       # reversed 9 days later: 4 days past T+5
        ("2026-07-10", "3000.00"): ON_TIME,    # REVERSAL-ATW for the first of two identical withdrawals
        ("2026-08-16", "6850.00"): ON_TIME,    # REVERSAL FAILED TXN the next day
    }
    assert a.total_owed_inr == 400


def test_sbi_planted_cases():
    a, found = _found("sbi_account_statement.xlsx")
    assert found == {("2026-06-04", "412.00"): ON_TIME,    # UPI/REF, a fresh reference, 2 days on
                     ("2026-06-12", "2899.00"): CONFIRM}   # UPI/REF 8 days on: looks late, so asked
    assert a.total_owed_inr == 0


client = TestClient(app)


@pytest.mark.parametrize("name", HDFC + SBI)
def test_the_web_app_identifies_each_download(name):
    body = {"file": base64.b64encode((REAL / name).read_bytes()).decode(), "filename": name}
    got = client.post("/api/statement", json=body).json()
    if "locked" in name:
        assert got["locked"] and not got["wrong_password"]
        got = client.post("/api/statement", json={**body, "password": mk.SBI_PASSWORD}).json()
    bank, count = ("HDFC", 40) if name.startswith("hdfc") else ("SBI", 20)
    assert (got["locked"], got["bank"], got["transactions"]) == (False, bank, count)
