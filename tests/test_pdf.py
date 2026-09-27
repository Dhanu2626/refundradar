"""Statement PDFs (DECISIONS.md, D18): SBI's and HDFC's tables rebuilt from a
PDF's characters, then read by the same strict readers as a spreadsheet,
running balance included.

Every PDF here is synthetic (samples/realistic/ and samples/pdf_layouts/,
drawn by tools/make_realistic_statements.py): the banks' layouts as known, and
the other ways report writers draw a table. No real SBI or HDFC PDF has been
read yet, so these prove the reader against layouts as known, nothing more.
"""

import base64
import csv
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refundradar import pdftable
from refundradar.audit import build_audit
from refundradar.formats import EncryptedStatement, WrongPassword, sniff
from refundradar.parser import NO_BANK_TABLE, parse_statement_bytes, parse_statement_file
from refundradar.pdftable import MARK, _join, _Piece, pdf_rows
from refundradar.webapp import VERIFICATION_PDF, app

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "samples" / "realistic"
LAYOUTS = ROOT / "samples" / "pdf_layouts"
sys.path.insert(0, str(ROOT / "tools"))
import make_realistic_statements as mk  # noqa: E402

FIELDS = ("txn_date", "amount", "is_debit", "narration", "ref", "alt_ref", "channel", "balance",
          "bank")
TWIN = {"hdfc": REAL / "hdfc_netbanking.xls", "sbi": REAL / "sbi_account_statement.xlsx"}
client = TestClient(app)


def _key(t, fields=FIELDS):
    return tuple(getattr(t, f) for f in fields)


def _read(path: Path):
    return parse_statement_file(path, password=mk.SBI_PASSWORD if "locked" in path.name else None)


def _twin(name: str):
    return _read(TWIN["hdfc" if name.startswith("hdfc") else "sbi"])


# --- read exactly as the spreadsheet --------------------------------------------

@pytest.mark.parametrize("name", ["hdfc_netbanking.pdf", "sbi_account_statement.pdf",
                                  "sbi_account_statement_locked.pdf"])
def test_the_banks_pdfs_read_exactly_as_their_spreadsheets(name):
    # every transaction: date, amount, direction, narration, both references,
    # channel and balance, character for character
    got, want = _read(REAL / name), _twin(name)
    assert len(got) == len(want) == (40 if name.startswith("hdfc") else 20)
    assert [_key(t) for t in got] == [_key(t) for t in want]


@pytest.mark.parametrize("name", [
    "hdfc_breaks_after_hyphens.pdf",        # lines broken after - and /, too
    "hdfc_heading_on_first_page_only.pdf",  # page 2 has rows but no heading
    "hdfc_rows_split_by_page_breaks.pdf",   # a row's last lines under page 2's heading
    "hdfc_words_drawn_apart.pdf",           # no space characters, only gaps
    "hdfc_courier.pdf",                     # dates and references wrap too
    "hdfc_heading_drawn_twice.pdf",         # fake bold, heading cells centred
    "sbi_breaks_after_hyphens.pdf",
    "sbi_times.pdf",
])
def test_other_ways_of_drawing_the_table_read_the_same(name):
    got, want = _read(LAYOUTS / name), _twin(name)
    assert [_key(t) for t in got] == [_key(t) for t in want]


def test_a_statement_listed_newest_first_reads_the_same():
    got = _read(LAYOUTS / "hdfc_newest_first.pdf")
    assert [_key(t) for t in got[::-1]] == [_key(t) for t in _twin("hdfc")]


@pytest.mark.parametrize("name, lost", [
    ("hdfc_breaks_anywhere.pdf", 1),        # text broken at any character
    ("sbi_breaks_anywhere.pdf", 4),
    ("sbi_rows_split_by_page_breaks.pdf", 1),
    ("sbi_words_drawn_apart.pdf", 1),
])
def test_a_space_that_fell_on_a_line_break_can_be_lost_and_nothing_else(name, lost):
    # a PDF doesn't record a space dropped where a line broke ("SAMPLE" /
    # "FRIEND" reads SAMPLEFRIEND): the narration can lose it, but every date,
    # amount, balance, reference and channel reads exactly
    got, want = _read(LAYOUTS / name), _twin(name)
    rest = tuple(f for f in FIELDS if f != "narration")
    assert [_key(t, rest) for t in got] == [_key(t, rest) for t in want]
    assert [t.narration.replace(" ", "") for t in got] == \
        [t.narration.replace(" ", "") for t in want]
    assert sum(g.narration != w.narration for g, w in zip(got, want)) == lost


def test_the_planted_cases_are_found_in_the_pdfs():
    from datetime import date
    for name in ("hdfc_netbanking.pdf", "sbi_account_statement.pdf"):
        a = build_audit(_read(REAL / name), set(), as_of=date(2026, 9, 1))
        b = build_audit(_twin(name), set(), as_of=date(2026, 9, 1))
        assert [(i.txn.txn_date, i.txn.amount, i.status) for i in a.incidents] == \
            [(i.txn.txn_date, i.txn.amount, i.status) for i in b.incidents]
        assert a.total_owed_inr == b.total_owed_inr == (400 if name.startswith("hdfc") else 0)


# --- refused, never guessed ---------------------------------------------------------

@pytest.mark.parametrize("name", ["hdfc_rows_centred.pdf", "hdfc_rows_bottom_aligned.pdf",
                                  "sbi_rows_centred.pdf"])
def test_rows_not_read_from_their_date_down_are_refused(name):
    # cells centred or bottom-aligned in their row put a transaction's first
    # lines above its date, where they would be read into the one before
    with pytest.raises(ValueError, match="sits in the table without belonging to a transaction"):
        _read(LAYOUTS / name)


def test_a_misprinted_amount_stops_the_audit_naming_the_page_and_row():
    with pytest.raises(ValueError) as e:
        _read(LAYOUTS / "hdfc_amount_misprinted.pdf")
    assert str(e.value).startswith(
        "Page 1, row 11, Closing Balance: the statement says 101,732.45, but page 1, "
        "row 10's balance and the rows between lead to 101,705.45")


def test_a_note_between_two_transactions_is_not_read_into_either():
    with pytest.raises(ValueError, match="^Page 1, line 32: 'Balance brought forward from the "
                                         "previous period' sits in the table"):
        _read(LAYOUTS / "hdfc_note_between_rows.pdf")


def test_a_transaction_after_the_statement_summary_stops_the_audit():
    with pytest.raises(ValueError, match="^Page 2, line 30: a dated row with an amount after "
                                         "the statement summary on page 2, line 24"):
        _read(LAYOUTS / "hdfc_row_after_summary.pdf")


def test_another_banks_pdf_is_refused():
    with pytest.raises(ValueError, match=f"^{NO_BANK_TABLE}$"):
        _read(LAYOUTS / "other_bank.pdf")


@pytest.mark.parametrize("name", ["scanned.pdf", "scanned_with_hidden_text.pdf"])
def test_a_scan_is_refused_even_with_machine_read_text_hidden_in_it(name):
    # character recognition can misread an amount: only text the bank drew is read
    with pytest.raises(ValueError, match="^This PDF has no readable text: it is a scan"):
        _read(LAYOUTS / name)


@pytest.mark.parametrize("data", [b"%PDF-1.7\n1 0 obj\n", "half", "holed"])
def test_a_damaged_pdf_is_refused(data):
    good = (REAL / "hdfc_netbanking.pdf").read_bytes()
    data = {"half": good[: len(good) // 2], "holed": good[:3000] + bytes(200) + good[3200:]}.get(
        data, data)
    with pytest.raises(ValueError, match="^This PDF is damaged or incomplete"):
        parse_statement_bytes(data)


def test_text_drawn_as_codes_is_refused(monkeypatch):
    # fonts that don't say which letters they draw come out as (cid:NN)
    real = pdftable._pages

    def coded(data, password):
        pages, locked = real(data, password)
        for page in pages:
            for c in page[::7]:
                c.text = "(cid:17)"
        return pages, locked

    monkeypatch.setattr(pdftable, "_pages", coded)
    with pytest.raises(ValueError, match="^This PDF's text comes out as codes"):
        pdf_rows((REAL / "hdfc_netbanking.pdf").read_bytes())


def test_a_pdf_with_a_little_junk_before_its_header_is_still_a_pdf():
    data = b"\r\n" * 8 + (REAL / "hdfc_netbanking.pdf").read_bytes()
    assert sniff(data) == "pdf" and len(parse_statement_bytes(data)) == 40


# --- locked PDFs ------------------------------------------------------------------------

def test_a_locked_pdf_asks_for_its_password_and_opens_with_the_right_one():
    data = (REAL / "sbi_account_statement_locked.pdf").read_bytes()
    with pytest.raises(EncryptedStatement) as e:
        pdf_rows(data)
    assert not isinstance(e.value, WrongPassword)
    with pytest.raises(WrongPassword, match="^That password doesn't open this PDF"):
        pdf_rows(data, password="54321")
    rows = pdf_rows(data, password=mk.SBI_PASSWORD)
    assert rows.locked and not pdf_rows((REAL / "sbi_account_statement.pdf").read_bytes()).locked
    assert list(rows) == list(pdf_rows((REAL / "sbi_account_statement.pdf").read_bytes()))


def test_the_command_line_reads_a_locked_pdf(capsys):
    from refundradar.__main__ import main
    locked = str(REAL / "sbi_account_statement_locked.pdf")
    assert main(["audit", locked]) == 1
    assert "Locked file: This PDF is password-protected by your bank." in capsys.readouterr().out
    assert main(["audit", locked, "--password", "54321"]) == 1
    assert "That password doesn't open this PDF." in capsys.readouterr().out
    assert main(["audit", locked, "--password", mk.SBI_PASSWORD]) == 0
    assert "20 lines" in capsys.readouterr().out


# --- joining a wrapped cell's lines -------------------------------------------------------
# A column whose text may run to x=100; each piece: text, where it ends, the
# width of its first character, whether a space is on it.

def _p(text, x1, first=4.0):
    return _Piece(text, x1, first, " " in text)


def test_a_reference_broken_across_two_lines_is_put_back_whole():
    got = _join([_p("UPI-IRCTC-IRCTCWEBUPI@SBI-SBIN0016209-61", 99.5),
                 _p("6112345604-TICKET", 60)], 100, False)
    assert got == "UPI-IRCTC-IRCTCWEBUPI@SBI-SBIN0016209-616112345604-TICKET"


def test_a_line_that_stopped_short_broke_at_a_space():
    # the next line's first character would have fitted: it didn't break inside a word
    assert _join([_p("IMPS-616012345603-SAMPLE", 70), _p("FRIEND-SBIN-XXXXXXX9876", 90)], 100,
                 False) == "IMPS-616012345603-SAMPLE FRIEND-SBIN-XXXXXXX9876"


def test_a_line_with_a_space_on_it_broke_at_a_space_even_at_the_edge():
    assert _join([_p("WDL TFR UPI/DR/615312340001/SAMPLE", 98.5), _p("LANDLORD/HDFC", 60)],
                 100, False) == "WDL TFR UPI/DR/615312340001/SAMPLE LANDLORD/HDFC"


def test_after_a_hyphen_nothing_is_added_but_a_lone_dash_keeps_its_space():
    assert _join([_p("UPI-SWIGGY-SWIGGY.STORES@AXB-", 80), _p("UTIB0000100", 50)], 100,
                 False) == "UPI-SWIGGY-SWIGGY.STORES@AXB-UTIB0000100"
    assert _join([_p("CHQ DEP - MICR CTS - HYDERABAD -", 99), _p("000123", 30)], 100,
                 False) == "CHQ DEP - MICR CTS - HYDERABAD - 000123"


def test_a_word_is_not_glued_onto_a_reference():
    assert _join([_p("CHARGES", 99), _p("616012345603 INCL GST", 90)], 100,
                 False) == "CHARGES 616012345603 INCL GST"


def test_text_broken_anywhere_is_joined_as_it_is():
    assert _join([_p("WDL TFR UPI/DR/61531", 99.2), _p("2340001/SAMPLE", 60)], 100,
                 True) == "WDL TFR UPI/DR/615312340001/SAMPLE"


# --- the web app ---------------------------------------------------------------------------

def _check(name, **extra):
    data = ((REAL if (REAL / name).exists() else LAYOUTS) / name).read_bytes()
    return client.post("/api/statement", json={
        "file": base64.b64encode(data).decode(), "filename": name, **extra})


@pytest.mark.parametrize("name, bank, count", [("hdfc_netbanking.pdf", "HDFC", 40),
                                               ("sbi_account_statement.pdf", "SBI", 20)])
def test_the_web_app_says_what_the_pdf_is_and_hands_back_its_rows(name, bank, count):
    s = _check(name).json()
    assert (s["locked"], s["bank"], s["file_type"], s["transactions"], s["password_used"]) == \
        (False, bank, "PDF", count, False)
    assert s["verification"] == VERIFICATION_PDF[bank] and "synthetically tested" in s["verification"]
    # later steps get the rows read, not the PDF: no reading it again, no password
    rows = base64.b64decode(s["unlocked_file"]).decode("utf-8")
    assert rows.startswith(MARK + "\n")
    assert list(csv.reader(io.StringIO(rows)))[1:] == \
        [list(r) for r in pdf_rows(((REAL / name).read_bytes()))]
    audit = client.post("/api/audit", json={"file": s["unlocked_file"], "filename": name,
                                            "as_of": "2026-09-01"}).json()
    twin = TWIN["hdfc" if bank == "HDFC" else "sbi"]
    want = client.post("/api/audit", json={"file": base64.b64encode(twin.read_bytes()).decode(),
                                           "filename": twin.name, "as_of": "2026-09-01"}).json()
    assert audit["audit"] == want["audit"] and audit["candidates"] == want["candidates"]
    assert audit["statement"]["verification"] == VERIFICATION_PDF[bank]  # still says PDF
    assert want["statement"]["verification"] != VERIFICATION_PDF[bank]


def test_the_web_app_opens_a_locked_pdf_once():
    name = "sbi_account_statement_locked.pdf"
    assert _check(name).json() == {"locked": True, "wrong_password": False, "filename": name}
    assert _check(name, password="54321").json()["wrong_password"] is True
    s = _check(name, password=mk.SBI_PASSWORD).json()
    assert (s["locked"], s["password_used"], s["file_type"], s["transactions"]) == \
        (False, True, "PDF", 20)
    assert mk.SBI_PASSWORD.encode() not in base64.b64decode(s["unlocked_file"])


@pytest.mark.parametrize("name, says", [
    ("other_bank.pdf", "Could not find a statement table in other_bank.pdf. RefundRadar reads "
                       "SBI statements (.xlsx, .xls, .csv or PDF), HDFC statements"),
    ("scanned.pdf", "This PDF has no readable text: it is a scan or a photo of a statement."),
    ("hdfc_amount_misprinted.pdf", "Page 1, row 11, Closing Balance: the statement says"),
])
def test_the_web_app_refuses_what_the_reader_refuses_in_its_words(name, says):
    res = _check(name)
    assert res.status_code == 400 and res.json()["detail"].startswith(says)


def test_the_committed_pdfs_are_what_the_generator_draws():
    pytest.importorskip("reportlab")
    pytest.importorskip("PIL")
    assert (REAL / "hdfc_netbanking.pdf").read_bytes() == mk.hdfc_pdf()
    assert (REAL / "sbi_account_statement.pdf").read_bytes() == mk.sbi_pdf()
    assert sorted(p.name for p in LAYOUTS.glob("*.pdf")) == sorted(mk.LAYOUTS)
    for name in mk.LAYOUTS:
        assert (LAYOUTS / name).read_bytes() == mk.layout(name), name
