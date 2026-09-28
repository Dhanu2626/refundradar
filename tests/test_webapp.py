"""The web layer: every endpoint, the happy path and the failure path."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refundradar.webapp import app

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
AS_OF = "2026-07-23"

client = TestClient(app)


@pytest.fixture(scope="module")
def demo_csv():
    return (SAMPLES / "demo_statement.csv").read_text(encoding="utf-8-sig")


def test_index_serves_the_app_upload_first():
    res = client.get("/")
    assert res.status_code == 200 and "RefundRadar" in res.text
    landing = res.text.split('<section id="screen-drop"', 1)[1].split("</section>", 1)[0]
    # the first thing to do is give it your statement; the sample is a link after that
    first = re.search(r"<button[^>]*>(?:<svg.*?</svg>)?([^<]+)", landing).group(1)
    assert first == "Upload bank statement"
    assert "Drag &amp; drop your bank statement here" in landing
    assert landing.index('id="drop"') < landing.index('id="demo-btn" class="link"')
    assert "<b>SBI</b>" in landing and "<b>HDFC</b>" in landing
    assert "Other banks, and scanned or photographed statements, aren't supported." in landing
    assert "not yet verified against a real SBI PDF" in landing  # PDFs: synthetic only (D18)


def _never_refunded_ref():
    """The sample's planted payment that never came back, from its answer key."""
    truth = json.loads((SAMPLES / "ground_truth.json").read_text())
    [ref] = [i["ref"] for i in truth["incidents"]
             if i["is_incident"] and i["refund_date"] is None]
    return ref


def test_demo_endpoint_serves_the_sample_without_its_answers(demo_csv):
    res = client.get("/api/demo")
    assert res.status_code == 200
    assert res.json() == {"csv": demo_csv}  # nothing is confirmed for the user (D6)


def test_audit_endpoint_without_confirmation(demo_csv):
    res = client.post("/api/audit", json={"csv": demo_csv, "as_of": AS_OF})
    assert res.status_code == 200
    a = res.json()["audit"]
    assert a["total_owed_inr"] == 1400
    assert a["on_time_count"] == 1
    assert res.json()["candidates"], "unflagged debits offered for confirmation"


def test_audit_endpoint_with_confirmation(demo_csv):
    ref = _never_refunded_ref()
    res = client.post("/api/audit",
                      json={"csv": demo_csv, "confirmed": [ref], "as_of": AS_OF})
    a = res.json()["audit"]
    assert a["total_owed_inr"] == 1400 + 3700
    from decimal import Decimal
    assert Decimal(a["stuck_amount"]) == Decimal(2499)


def test_complaint_endpoint(demo_csv):
    ref = _never_refunded_ref()
    res = client.post("/api/complaint", json={
        "csv": demo_csv, "confirmed": [ref], "as_of": AS_OF,
        "name": "Dhanush Jangadi", "account_last4": "2626",
        "contact": "test@example.com",
    })
    assert res.status_code == 200
    assert "Rs.5100" in res.text
    assert "RBI/2019-20/67" in res.text


def test_bad_file_gets_clear_400():
    res = client.post("/api/audit", json={"csv": "not,a,statement\n1,2,3\n"})
    assert res.status_code == 400
    assert "Unrecognized statement format" in res.json()["detail"]


# --- Statement files: HDFC through the web app (synthetic samples only) -----

import base64
import csv
import io
from datetime import date

from refundradar.audit import build_audit
from refundradar.parser import parse_statement_file

HDFC_CSV = SAMPLES / "hdfc_statement.csv"
HDFC_AS_OF = "2026-04-30"


def _upload(data: bytes, name: str, **extra):
    return client.post("/api/audit", json={
        "file": base64.b64encode(data).decode(), "filename": name,
        "as_of": HDFC_AS_OF, **extra})


def _xlsx(path) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    for row in csv.reader(path.read_text(encoding="utf-8").splitlines()):
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.parametrize("name, read", [
    ("hdfc_statement.csv", lambda: HDFC_CSV.read_bytes()),
    ("hdfc_statement.xls", lambda: (SAMPLES / "hdfc_statement.xls").read_bytes()),
    ("hdfc_statement.xlsx", lambda: _xlsx(HDFC_CSV)),
])
def test_hdfc_upload_runs_the_existing_parser_and_audit(name, read):
    res = _upload(read(), name)
    assert res.status_code == 200
    body = res.json()
    assert body["statement"] == {
        "filename": name, "format": "HDFC", "transactions": 22,
        "verification": "HDFC export: synthetically tested, not yet verified "
                        "against a real HDFC export."}
    assert body["summary"] == {"transactions": 22, "refunds_found": 5, "matched": 5,
                               "needs_confirmation": 0, "unable_to_match": 0}
    assert body["audit"]["total_owed_inr"] == 1400
    # the same verdicts the CLI reaches for this statement
    cli = build_audit(parse_statement_file(HDFC_CSV), as_of=date(2026, 4, 30))
    assert [i["status"] for i in body["audit"]["incidents"]] == [i.status for i in cli.incidents]


@pytest.mark.parametrize("old, new, error", [
    (b'450.00,"87,500.00"', b'450.00 Cr,"87,500.00"', "Row 15, Deposit Amt.: '450.00 Cr'"),
    (b"STATEMENT SUMMARY  :-,,,,,,", b"STATEMENT SUMMARY  :-,,,,,,\n05/04/26,PASTED,,05/04/26,,10.00,",
     "a dated row with an amount after the statement summary"),
], ids=["unreadable amount", "row pasted below the summary"])
def test_unreadable_hdfc_statement_gets_the_parsers_words_and_no_result(old, new, error):
    data = HDFC_CSV.read_bytes()
    assert old in data
    res = _upload(data.replace(old, new, 1), "hdfc.csv")
    assert res.status_code == 400
    assert error in res.json()["detail"]
    assert "audit" not in res.json()  # never a partial result


def test_generic_csv_upload_matches_the_text_path(demo_csv):
    by_text = client.post("/api/audit", json={"csv": demo_csv, "as_of": AS_OF}).json()
    by_file = _upload(demo_csv.encode(), "demo_statement.csv", as_of=AS_OF).json()
    assert by_file["statement"]["format"] == "generic"
    assert by_file["audit"] == by_text["audit"]


SEVERAL_ORIGINS = ("Date,Narration,Ref,Debit,Credit,Balance\n"
                   "01-02-2026,UPI/DR/600000000001/PAYTMQR1@PAYTM/A,,500.00,,9500.00\n"
                   "03-02-2026,UPI/DR/600000000002/PAYTMQR2@PAYTM/B,,500.00,,9000.00\n"
                   "25-02-2026,UPI/REF/690000000001/CR,,,500.00,9500.00\n")


def test_reversal_with_several_possible_payments_is_offered_not_claimed():
    body = client.post("/api/audit", json={"csv": SEVERAL_ORIGINS, "as_of": AS_OF}).json()
    assert body["audit"]["incidents"] == [] and body["audit"]["total_owed_inr"] == 0
    [item] = body["unmatched"]
    assert item["refund"]["txn_id"] == 2
    assert [c["txn_id"] for c in item["candidates"]] == [0, 1]
    assert body["summary"]["unable_to_match"] == 1
    # the user picks payment B: claimed only up to that reversal's date
    body = client.post("/api/audit", json={"csv": SEVERAL_ORIGINS, "pairs": [[1, 2]],
                                           "as_of": AS_OF}).json()
    [inc] = body["audit"]["incidents"]
    assert (inc["status"], inc["compensation_inr"], inc["refund_date"]) == (
        "refunded_late", 1700, "2026-02-25")
    assert body["unmatched"] == []


COMPETING = ("Date,Narration,Ref,Debit,Credit,Balance\n"
             "10-02-2026,UPI/DR/604112345678/9876543210@OKHDFC/RENT,,2000.00,,8000.00\n"
             "12-02-2026,UPI/CR/605300001111/RAVI KUMAR,,,2000.00,10000.00\n"
             "25-02-2026,UPI/REF/690000000009/CR,,,2000.00,12000.00\n")


def test_confirmed_failure_with_competing_credits_lets_the_user_choose():
    asked = client.post("/api/audit", json={"csv": COMPETING, "as_of": AS_OF}).json()
    [inc] = asked["audit"]["incidents"]
    assert (inc["status"], inc["action"]) == ("needs_confirmation", "confirm_failed")
    ref = inc["ref"]
    body = client.post("/api/audit", json={"csv": COMPETING, "confirmed": [ref],
                                           "as_of": AS_OF}).json()
    [inc] = body["audit"]["incidents"]
    assert inc["action"] == "choose_refund"
    assert [c["txn_id"] for c in inc["candidates"]] == [1, 2]
    assert body["audit"]["total_owed_inr"] == 0 and body["unmatched"] == []
    body = client.post("/api/audit", json={"csv": COMPETING, "confirmed": [ref],
                                           "pairs": [[0, 1]], "as_of": AS_OF}).json()
    [inc] = body["audit"]["incidents"]
    assert (inc["status"], inc["compensation_inr"]) == ("refunded_late", 100)


@pytest.mark.parametrize("pairs", [[[2, 0]], [[0, 9]], [[0, 2], [1, 2]]],
                         ids=["refund as payment", "no such row", "one refund twice"])
def test_a_selection_that_does_not_fit_is_refused(pairs):
    res = client.post("/api/audit", json={"csv": SEVERAL_ORIGINS, "pairs": pairs})
    assert res.status_code == 400


def test_password_protected_file_gets_the_readers_message(monkeypatch):
    import refundradar.webapp as web
    from refundradar.formats import EncryptedStatement

    def locked(_data):
        raise EncryptedStatement("This statement is password-protected by your bank.")
    monkeypatch.setattr(web, "parse_statement_bytes", locked)
    res = _upload(b"\xd0\xcf\x11\xe0", "locked.xlsx")
    assert res.status_code == 400 and "password-protected" in res.json()["detail"]


def test_file_that_is_no_statement_says_what_the_web_app_reads():
    res = _upload(b"foo,bar\n1,2\n", "notes.csv")
    assert res.status_code == 400
    assert res.json()["detail"].startswith("Could not find a statement table in notes.csv.")


DELIMITED = (  # HDFC's Delimited layout, as tests/test_hdfc.py infers it
    " Date     ,Narration                                                       "
    ",Value Dat,Debit Amount       ,Credit Amount      ,Chq/Ref Number   ,Closing Balance\n"
    " 03/02/26 ,UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-PAYMENT  "
    ",03/02/26 ,           450.00  ,             0.00  ,0000603412345678 ,       39550.00\n"
    " 05/02/26 ,UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-REVERSAL "
    ",05/02/26 ,             0.00  ,           450.00  ,0000603412345678 ,       40000.00\n"
)


def test_delimited_txt_upload_is_read_as_hdfc():
    res = _upload(DELIMITED.encode(), "hdfc_delimited.txt")
    assert res.status_code == 200
    body = res.json()
    assert (body["statement"]["format"], body["statement"]["transactions"]) == ("HDFC", 2)
    assert [i["status"] for i in body["audit"]["incidents"]] == ["refunded_on_time"]


@pytest.mark.parametrize("data", [
    b"Shopping list\nmilk\neggs\n", b"", b"   \n\n", bytes(range(256)) * 4,
    "hello\n".encode("utf-16"),
], ids=["notes", "empty", "blank lines", "binary", "utf-16 text"])
def test_txt_that_is_no_statement_is_refused_and_says_what_is_read(data):
    # the picker offers .txt, so any text file can arrive: it is refused whole,
    # and the refusal lists .txt among the formats the web app reads
    res = _upload(data, "notes.txt")
    assert res.status_code == 400 and set(res.json()) == {"detail"}
    detail = res.json()["detail"]
    assert "notes.txt" in detail and ".txt" in detail.replace("notes.txt", "")


def test_damaged_or_missing_statement_gets_a_clear_400():
    res = client.post("/api/audit", json={"file": "not base64!", "filename": "x.xls"})
    assert (res.status_code, res.json()["detail"]) == (
        400, "The file arrived damaged. Choose it again.")
    assert client.post("/api/audit", json={}).status_code == 400


# --- SBI through the web app, now that its reader drops nothing (D16) -------

SBI_XLSX = SAMPLES / "sbi_statement.xlsx"
SBI_AS_OF = "2026-09-01"
SBI_CSV = ("Txn Date,Value Date,Description,Ref No./Cheque No.,Branch Code,Debit,Credit,Balance\n"
           '3 Feb 2026,3 Feb 2026,TO TRANSFER-UPI/DR/504212345678/SWIGGY.ORDER@ICICI/PAY,'
           '504212345678,1234,450.00,,"39,550.00"\n')


def test_sbi_export_is_audited_by_the_web_app():
    res = _upload(SBI_XLSX.read_bytes(), "sbi_statement.xlsx", as_of=SBI_AS_OF)
    assert res.status_code == 200
    data = res.json()
    assert data["statement"]["format"] == "SBI"
    assert "field-tested on one real SBI statement" in data["statement"]["verification"]
    assert data["summary"]["transactions"] == 20
    # the ATM cash and the card payment print no reference: offered by their row
    no_ref = {(c["row"], c["amount"]) for c in data["candidates"] if c["ref"] is None}
    assert {(5, "5000.00"), (8, "1845.50")} <= no_ref


def test_sbi_row_the_reader_cannot_read_is_refused_not_skipped():
    res = _upload(SBI_CSV.replace("450.00,,", "450.00 Dr,,").encode(), "sbi.csv")
    assert res.status_code == 400
    assert res.json()["detail"] == "Row 2, Debit: '450.00 Dr' is not a plain positive number."


def test_another_banks_export_is_refused_by_name():
    other = SBI_CSV.replace("Txn Date", "Date").replace("Ref No./Cheque No.", "Chq No")
    res = _upload(other.encode(), "icici.csv")
    assert res.status_code == 400
    assert "not laid out the way SBI or HDFC exports are" in res.json()["detail"]


def test_a_damaged_pdf_is_refused_with_what_to_do():
    # PDFs are read (tests/test_pdf.py); one that isn't whole is refused, not guessed at
    res = _upload(b"%PDF-1.7\n1 0 obj\n", "statement.pdf")
    assert (res.status_code, res.json()["detail"]) == (400, (
        "This PDF is damaged or incomplete, so it can't be read. Download it again."))


# --- Detecting the statement before the audit, and unlocking it (D17) -------

def _check(data: bytes, name: str, **extra):
    return client.post("/api/statement", json={
        "file": base64.b64encode(data).decode(), "filename": name, **extra})


def _locked(password="Sample@2626") -> bytes:
    import io
    from msoffcrypto.format.ooxml import OOXMLFile
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(SBI_XLSX.read_bytes())).encrypt(password, out)
    return out.getvalue()


@pytest.mark.parametrize("name, bank, kind, count, first, last", [
    ("sbi_statement.xlsx", "SBI", "Excel workbook (.xlsx)", 20, "2026-06-01", "2026-08-10"),
    ("hdfc_statement.xls", "HDFC", "Excel 97-2003 workbook (.xls)", 22, "2026-02-01", "2026-03-31"),
    ("hdfc_statement.csv", "HDFC", "CSV or delimited text", 22, "2026-02-01", "2026-03-31"),
])
def test_statement_is_identified_before_it_is_audited(name, bank, kind, count, first, last):
    res = _check((SAMPLES / name).read_bytes(), name)
    assert res.status_code == 200
    got = res.json()
    assert (got["locked"], got["bank"], got["file_type"], got["transactions"],
            got["first"], got["last"]) == (False, bank, kind, count, first, last)
    assert got["payments"] + got["credits"] == count and got["unlocked_file"] is None
    assert "audit" not in got  # nothing is analysed until the user asks


def test_the_sample_statement_is_identified_as_generic_csv(demo_csv):
    got = client.post("/api/statement", json={"csv": demo_csv}).json()
    assert (got["bank"], got["file_type"], got["locked"]) == ("generic", "CSV or delimited text", False)


def test_a_locked_statement_asks_for_its_password():
    locked = _locked()
    got = _check(locked, "sbi_statement.xlsx").json()
    assert got == {"locked": True, "wrong_password": False, "filename": "sbi_statement.xlsx"}
    wrong = _check(locked, "sbi_statement.xlsx", password="not it").json()
    assert (wrong["locked"], wrong["wrong_password"]) == (True, True)
    # auditing it without opening it first is refused, not guessed at
    res = _upload(locked, "sbi_statement.xlsx")
    assert res.status_code == 400 and "password-protected" in res.json()["detail"]


def test_the_password_opens_it_once_and_the_open_file_is_audited():
    got = _check(_locked(), "sbi_statement.xlsx", password="Sample@2626").json()
    assert (got["locked"], got["bank"], got["transactions"]) == (False, "SBI", 20)
    opened = base64.b64decode(got["unlocked_file"])
    assert opened == SBI_XLSX.read_bytes()  # the workbook inside, byte for byte
    assert "Sample@2626" not in json.dumps(got)  # the password is never sent back
    res = _upload(opened, "sbi_statement.xlsx", as_of=SBI_AS_OF)
    assert res.status_code == 200 and res.json()["summary"]["transactions"] == 20


def test_an_unreadable_statement_is_refused_at_detection():
    res = _check(b"Dear diary, nothing to see.\n", "notes.txt")
    assert res.status_code == 400 and "Could not find a statement table in notes.txt" in res.json()["detail"]


def test_complaint_from_an_uploaded_hdfc_xls():
    res = client.post("/api/complaint", json={
        "file": base64.b64encode((SAMPLES / "hdfc_statement.xls").read_bytes()).decode(),
        "filename": "hdfc_statement.xls", "as_of": HDFC_AS_OF,
        "name": "A. Sample Customer", "account_last4": "1234", "contact": "sample@example.com"})
    assert res.status_code == 200
    assert "Rs.1400" in res.text and "RBI/2019-20/67" in res.text


def test_index_accepts_statement_files_and_says_what_is_unverified():
    html = client.get("/").text
    # the picker offers every format the web app reads, HDFC's Delimited .txt and PDFs too
    accept = re.search(r'id="file" accept="([^"]*)"', html).group(1)
    assert set(accept.split(",")) == {".csv", ".xls", ".xlsx", ".txt", ".pdf"}
    assert "Unable to conclusively match" in html
    assert "synthetically tested" in html


def test_amounts_keep_their_paise_and_whole_rupees_show_none():
    # the page's own formatter, run as a browser runs it: ₹1,675.30, never ₹1,675.3
    node = shutil.which("node")
    if node is None:
        pytest.skip("runs the page's JavaScript with Node.js")
    inr = re.search(r"const inr = \(n\) =>.*?;\n", client.get("/").text, re.S).group(0)
    amounts = ["1675.30", "5.90", "0.50", "123456.70", "16000.00", "412.00", 400, 0, "0"]
    run = subprocess.run([node, "-e", f"{inr}console.log(JSON.stringify({json.dumps(amounts)}.map(inr)))"],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(run.stdout) == ["₹1,675.30", "₹5.90", "₹0.50", "₹1,23,456.70", "₹16,000", "₹412",
                                      "₹400", "₹0", "₹0"]


def test_never_reversed_payment_is_offered_then_claimed_only_once_confirmed():
    # D6: a payment that failed and never came back looks, on the statement,
    # like any payment that went through; it is offered for confirmation and
    # claimed only after the user says it failed
    first = _upload(HDFC_CSV.read_bytes(), "hdfc_statement.csv").json()
    assert [c["amount"] for c in first["candidates"] if c["ref"] == "607912345678"] == ["2499.00"]
    assert all(i["ref"] != "607912345678" for i in first["audit"]["incidents"])
    second = _upload(HDFC_CSV.read_bytes(), "hdfc_statement.csv",
                     confirmed=["607912345678"]).json()
    [rent] = [i for i in second["audit"]["incidents"] if i["ref"] == "607912345678"]
    assert (rent["status"], rent["compensation_inr"]) == ("never_refunded", 4000)  # due 21 Mar
    assert second["audit"]["total_owed_inr"] == 800 + 600 + 4000
    assert all(c["ref"] != "607912345678" for c in second["candidates"])
