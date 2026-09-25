"""The web layer: every endpoint, the happy path and the failure path."""

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


def test_index_serves_the_app():
    res = client.get("/")
    assert res.status_code == 200
    assert "RefundRadar" in res.text
    assert "Drop your bank statement" in res.text


def test_demo_endpoint(demo_csv):
    res = client.get("/api/demo")
    assert res.status_code == 200
    data = res.json()
    assert data["csv"].startswith("Date,Narration")
    assert len(data["suggested_confirmed"]) == 1


def test_audit_endpoint_without_confirmation(demo_csv):
    res = client.post("/api/audit", json={"csv": demo_csv, "as_of": AS_OF})
    assert res.status_code == 200
    a = res.json()["audit"]
    assert a["total_owed_inr"] == 1400
    assert a["on_time_count"] == 1
    assert res.json()["candidates"], "unflagged debits offered for confirmation"


def test_audit_endpoint_with_confirmation(demo_csv):
    ref = client.get("/api/demo").json()["suggested_confirmed"][0]
    res = client.post("/api/audit",
                      json={"csv": demo_csv, "confirmed": [ref], "as_of": AS_OF})
    a = res.json()["audit"]
    assert a["total_owed_inr"] == 1400 + 3700
    from decimal import Decimal
    assert Decimal(a["stuck_amount"]) == Decimal(2499)


def test_complaint_endpoint(demo_csv):
    ref = client.get("/api/demo").json()["suggested_confirmed"][0]
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


def test_damaged_or_missing_statement_gets_a_clear_400():
    res = client.post("/api/audit", json={"file": "not base64!", "filename": "x.xls"})
    assert (res.status_code, res.json()["detail"]) == (
        400, "The file arrived damaged. Choose it again.")
    assert client.post("/api/audit", json={}).status_code == 400


def test_sbi_export_is_refused_by_the_web_app():
    # the SBI reader passes over unreadable rows; the web app shows no partial results
    sbi = ("Txn Date,Value Date,Description,Ref No./Cheque No.,Branch Code,Debit,Credit,Balance\n"
           '3 Feb 2026,3 Feb 2026,TO TRANSFER-UPI/DR/504212345678/SWIGGY.ORDER@ICICI/PAY,'
           '504212345678,1234,450.00,,"39,550.00"\n')
    res = _upload(sbi.encode(), "sbi.csv")
    assert res.status_code == 400
    assert res.json()["detail"].startswith("This is an SBI export.")


def test_complaint_from_an_uploaded_hdfc_xls():
    res = client.post("/api/complaint", json={
        "file": base64.b64encode((SAMPLES / "hdfc_statement.xls").read_bytes()).decode(),
        "filename": "hdfc_statement.xls", "as_of": HDFC_AS_OF,
        "name": "A. Sample Customer", "account_last4": "1234", "contact": "sample@example.com"})
    assert res.status_code == 200
    assert "Rs.1400" in res.text and "RBI/2019-20/67" in res.text


def test_index_accepts_statement_files_and_says_what_is_unverified():
    html = client.get("/").text
    assert 'accept=".csv,.xls,.xlsx"' in html
    assert "Unable to conclusively match" in html
    assert "synthetically tested" in html
