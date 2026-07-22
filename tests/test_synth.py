"""The statement factory must be deterministic, honest, and balance-correct."""

from decimal import Decimal

from refundradar.synth import generate


def _rows_truth():
    return generate(seed=26)


def test_deterministic_for_same_seed():
    assert generate(seed=7) == generate(seed=7)


def test_different_seed_different_statement():
    assert generate(seed=1)[0] != generate(seed=2)[0]


def test_every_incident_debit_exists_in_statement():
    rows, truth = _rows_truth()
    refs_in_rows = {r["Ref"] for r in rows if r["Ref"]}
    for inc in truth["incidents"]:
        assert inc["ref"] in refs_in_rows, inc["note"]


def test_refunded_incidents_have_matching_credit_row():
    rows, truth = _rows_truth()
    for inc in truth["incidents"]:
        if inc["refund_date"] is None:
            continue
        credits = [r for r in rows if r["Ref"] == inc["ref"] and r["Credit"]]
        assert len(credits) == 1, inc["note"]
        assert Decimal(credits[0]["Credit"]) == Decimal(inc["amount"])


def test_never_refunded_incident_has_no_credit():
    rows, truth = _rows_truth()
    unrefunded = [i for i in truth["incidents"] if i["refund_date"] is None]
    assert len(unrefunded) == 1
    ref = unrefunded[0]["ref"]
    assert not [r for r in rows if r["Ref"] == ref and r["Credit"]]


def test_trap_is_marked_not_an_incident():
    _, truth = _rows_truth()
    traps = [i for i in truth["incidents"] if not i["is_incident"]]
    assert len(traps) == 1
    assert traps[0]["refund_date"] is not None
    assert traps[0]["compensation_inr"] is None


def test_planted_compensation_matches_rules_engine():
    _, truth = _rows_truth()
    by_note = {i["note"]: i for i in truth["incidents"]}
    late_upi = next(i for n, i in by_note.items() if "8 days late" in n)
    assert late_upi["days_late"] == 8
    assert late_upi["compensation_inr"] == 800
    late_atm = next(i for n, i in by_note.items() if "6 days late" in n)
    assert late_atm["days_late"] == 6
    assert late_atm["compensation_inr"] == 600


def test_running_balance_is_arithmetically_consistent():
    rows, _ = _rows_truth()
    balance = Decimal(40000)
    for r in rows:
        if r["Debit"]:
            balance -= Decimal(r["Debit"])
        else:
            balance += Decimal(r["Credit"])
        assert Decimal(r["Balance"]) == balance
    assert balance > 0
