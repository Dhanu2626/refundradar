"""A payment printed without any reference (ATM cash, PoS card, ACH debit) is
confirmed by its row on the statement, never by an invented reference, and
only when the user says so (DECISIONS.md, D6 and D14)."""

import base64
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refundradar.audit import build_audit
from refundradar.complaint import generate_complaint_pack
from refundradar.model import Transaction
from refundradar.parser import parse_statement_bytes
from refundradar.reconcile import CONFIRM, LATE, NEVER, reconcile
from refundradar.webapp import INDEX, app

client = TestClient(app)
SAMPLES = Path(__file__).resolve().parent.parent / "samples"
HDFC = (SAMPLES / "hdfc_statement.csv").read_bytes()
AS_OF = "2026-04-30"
NO_REF = "not printed on statement"

# Two cash withdrawals alike in every printed detail, a payment outside the
# 2019 circular, a payment with a reference, and a salary credit.
TWINS = (
    "Date,Narration,Ref,Debit,Credit,Balance\n"
    "01-02-2026,NEFT CR-ACME TECH PVT LTD-SALARY,ACMEN8224253216320001,,52000.00,52000.00\n"
    "05-02-2026,ATW-512967XX1234-S1CN100001-HYDERABAD,,5000.00,,47000.00\n"
    "05-02-2026,ATW-512967XX1234-S1CN100001-HYDERABAD,,5000.00,,42000.00\n"
    "06-02-2026,NEFT-DR-RENT PAYMENT-JANUARY,,15000.00,,27000.00\n"
    "07-02-2026,UPI/DR/612345678901/SHOP@OKAXIS/PAYMENT,,300.00,,26700.00\n"
).encode()
SALARY, CASH_A, CASH_B, NEFT, UPI = range(5)


def upload(data=HDFC, filename="hdfc_statement.csv", path="/api/audit", **extra):
    return client.post(path, json={
        "file": base64.b64encode(data).decode(), "filename": filename, "as_of": AS_OF, **extra})


def letter(data=HDFC, filename="hdfc_statement.csv", **extra):
    res = upload(data, filename, path="/api/complaint", name="A. Sample Customer",
                 account_last4="2626", contact="sample@example.com", **extra)
    assert res.status_code == 200, res.text
    return res.text


def no_ref_offers(body):
    return {c["row"]: c for c in body["candidates"] if c["ref"] is None}


def incident_rows(body):
    return {i["txn_id"]: i for i in body["audit"]["incidents"]}


# ---------------------------------------------------------------- visible, not claimed

def test_payments_without_a_reference_are_offered_by_their_row():
    body = upload().json()
    txns = parse_statement_bytes(HDFC)
    offers = no_ref_offers(body)
    # the two ACH debits and the MORE card payment; the DMart card payment is
    # already a finding (its refund was matched), so it isn't offered again
    assert sorted(offers) == [2, 9, 14]
    for row, c in offers.items():
        t = txns[row]
        assert t.is_debit and not t.ref and not t.alt_ref
        assert (c["date"], c["amount"], c["narration"]) == (
            t.txn_date.isoformat(), str(t.amount), t.narration)


def test_a_payment_without_a_reference_is_not_claimed_until_confirmed():
    body = upload().json()
    assert not set(no_ref_offers(body)) & set(incident_rows(body))
    assert body["audit"]["total_owed_inr"] == 800 + 600
    assert NO_REF not in letter()


# ---------------------------------------------------------------- confirmed by its row

def test_confirming_a_row_claims_exactly_that_payment():
    before = upload().json()
    after = upload(confirmed_rows=[9]).json()
    new = incident_rows(after)[9]
    assert (new["status"], new["ref"], new["amount"], new["date"]) == (
        "never_refunded", None, "1245.50", "2026-02-20")
    assert new["compensation_inr"] > 0
    assert after["audit"]["total_owed_inr"] == before["audit"]["total_owed_inr"] + new["compensation_inr"]
    assert 9 not in no_ref_offers(after)


def test_the_letter_prints_not_printed_on_statement_never_none_or_a_made_up_reference():
    text = letter(confirmed_rows=[9])
    [row] = [line for line in text.splitlines() if line.startswith("| ") and "1245.50" in line]
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert (cells[1], cells[3], cells[4], cells[6]) == ("2026-02-20", "1245.50", NO_REF, "NOT YET REVERSED")
    assert "| None |" not in text and "ref None" not in text


def test_nothing_else_changes_when_a_row_is_confirmed():
    before, after = upload().json(), upload(confirmed_rows=[9]).json()
    rest = {k: v for k, v in incident_rows(after).items() if k != 9}
    assert rest == incident_rows(before)
    assert [c for c in after["candidates"] if c["row"] != 9] == [
        c for c in before["candidates"] if c["row"] != 9]
    # and the reference-confirmed payment still works beside it
    both = upload(confirmed=["607912345678"], confirmed_rows=[9]).json()
    rent = [i for i in both["audit"]["incidents"] if i["ref"] == "607912345678"]
    assert [i["status"] for i in rent] == ["never_refunded"] and 9 in incident_rows(both)


def test_identical_payments_are_told_apart_by_their_row():
    first = upload(TWINS, "twins.csv").json()
    offers = no_ref_offers(first)
    assert sorted(offers) == [CASH_A, CASH_B]  # NEFT is outside the circular; UPI has a reference
    a, b = offers[CASH_A], offers[CASH_B]
    assert (a["date"], a["amount"], a["narration"]) == (b["date"], b["amount"], b["narration"])

    one = upload(TWINS, "twins.csv", confirmed_rows=[CASH_B]).json()
    assert list(incident_rows(one)) == [CASH_B]
    assert list(no_ref_offers(one)) == [CASH_A]

    both = upload(TWINS, "twins.csv", confirmed_rows=[CASH_A, CASH_B]).json()
    assert sorted(incident_rows(both)) == [CASH_A, CASH_B]
    text = letter(TWINS, "twins.csv", confirmed_rows=[CASH_A, CASH_B])
    assert len(re.findall(rf"\| 2026-02-05 \| .* \| 5000\.00 \| {NO_REF} \|", text)) == 2


@pytest.mark.parametrize("rows, why", [
    ([-1], "no such row"), ([5], "no such row"),
    ([SALARY], "a credit"), ([UPI], "a payment with a reference"),
    ([NEFT], "outside the 2019 circular"), ([CASH_A, CASH_A], "the same row twice"),
])
def test_a_row_that_cannot_be_confirmed_is_refused_whole(rows, why):
    res = upload(TWINS, "twins.csv", confirmed_rows=rows)
    assert res.status_code == 400, why
    assert set(res.json()) == {"detail"} and res.json()["detail"]


@pytest.mark.parametrize("rows", [["x"], [1.5], "1"])
def test_a_row_that_is_not_a_row_number_is_refused(rows):
    assert upload(TWINS, "twins.csv", confirmed_rows=rows).status_code == 422


def test_a_confirmed_row_with_competing_refunds_asks_then_takes_the_users_pick():
    data = TWINS + (
        "10-02-2026,ATM CASH NOT DISPENSED REV OF S1CN100001,,,5000.00,31700.00\n"
        "11-02-2026,ATM CASH NOT DISPENSED REV OF S1CN100001,,,5000.00,36700.00\n").encode()
    asked = upload(data, "twins.csv", confirmed_rows=[CASH_A]).json()
    inc = incident_rows(asked)[CASH_A]
    assert (inc["status"], inc["action"], [c["txn_id"] for c in inc["candidates"]]) == (
        "needs_confirmation", "choose_refund", [5, 6])
    picked = upload(data, "twins.csv", confirmed_rows=[CASH_A], pairs=[[CASH_A, 6]]).json()
    inc = incident_rows(picked)[CASH_A]
    assert (inc["status"], inc["refund_date"], inc["compensation_inr"]) == ("refunded_late", "2026-02-11", 100)


# ---------------------------------------------------------------- the reconciler

def _debit(ref):
    return Transaction(date(2026, 2, 5), Decimal("5000.00"), True,
                       "ATW-512967XX1234-S1CN100001-HYDERABAD", ref=ref, channel="atm")


def _credit(day, ref="ATMREV" + "0" * 6):
    return Transaction(date(2026, 2, day), Decimal("5000.00"), False,
                       "ATM CASH NOT DISPENSED REVERSAL", ref=ref, channel="atm")


@pytest.mark.parametrize("credits", [[], [14], [14, 16]],
                         ids=["never refunded", "refunded late", "competing refunds"])
def test_a_row_confirmed_payment_is_treated_like_a_reference_confirmed_one(credits):
    by_ref, by_row = _debit("111122223333"), _debit(None)
    cs = [_credit(d, f"99990000{d:04d}") for d in credits]
    [a] = reconcile([by_ref, *cs], {"111122223333"}, as_of=date(2026, 4, 30))
    [b] = reconcile([by_row, *cs], as_of=date(2026, 4, 30), confirmed_failed_txns=[by_row])
    same = lambda i: (i.status, i.ruling and i.ruling.compensation_inr, i.refund_date, len(i.candidates))
    assert same(a) == same(b)
    assert a.status == {0: NEVER, 1: LATE, 2: CONFIRM}[len(credits)]


def test_confirmation_by_row_is_only_for_payments_with_no_reference():
    with_ref, credit = _debit("111122223333"), _credit(14)
    assert reconcile([with_ref], as_of=date(2026, 4, 30), confirmed_failed_txns=[with_ref]) == []
    assert reconcile([credit], as_of=date(2026, 4, 30), confirmed_failed_txns=[credit]) == []
    outsider = _debit(None)  # not a row of this statement
    assert reconcile([_debit(None)], as_of=date(2026, 4, 30), confirmed_failed_txns=[outsider]) == []


def test_an_older_confirmed_payment_is_listed_with_not_printed_on_statement():
    old, recent = _debit(None), _debit(None)
    recent.txn_date = date(2027, 6, 1)
    audit = build_audit([old, recent], as_of=date(2027, 6, 30), confirmed_failed_txns=[old, recent])
    assert [i.time_barred for i in audit.incidents] == [True, False]
    text = generate_complaint_pack(audit, "A. Sample Customer", "2626", "sample@example.com")
    assert f"| 2027-06-01 | ATM / Micro-ATM cash withdrawal | 5000.00 | {NO_REF} |" in text
    assert f"- 2026-02-05 · Rs.5000.00 · ref {NO_REF} ·" in text
    assert "None" not in text


# ---------------------------------------------------------------- the page asks the same thing

def test_the_page_confirms_by_row_what_the_api_offers_by_row():
    page = INDEX.read_text(encoding="utf-8")
    assert 'data-row="${c.row}"' in page            # a payment without a reference carries its row
    assert "confirmedRows.add(Number(b.dataset.row))" in page
    assert "confirmed_rows: [...state.confirmedRows]" in page
