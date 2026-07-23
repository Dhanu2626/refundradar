"""D8 (time-barred flag) and the disclaimer: the honesty layer."""

from datetime import date

from refundradar.audit import build_audit, to_dict
from refundradar.complaint import generate_complaint_pack
from refundradar.model import make_transaction

AS_OF = date(2026, 7, 24)


def _failed_pair(txn_date, refund_date, ref, amount=1000):
    d = make_transaction(txn_date, amount, True,
                         f"UPI/DR/{ref}/PAYTMQR999@PAYTM/PAYMENT")
    c = make_transaction(refund_date, amount, False,
                         f"UPI/CR/{ref}/REV OF FAILED TXN")
    return [d, c]


def _audit_with_old_and_fresh():
    txns = (
        _failed_pair(date(2025, 3, 1), date(2025, 3, 20), "111122223333")   # old
        + _failed_pair(date(2026, 6, 1), date(2026, 6, 20), "444455556666")  # fresh
    )
    return build_audit(txns, as_of=AS_OF)


def test_old_incident_is_flagged_and_out_of_total():
    a = _audit_with_old_and_fresh()
    old = next(i for i in a.incidents if i.txn.ref == "111122223333")
    fresh = next(i for i in a.incidents if i.txn.ref == "444455556666")
    assert old.time_barred is True
    assert fresh.time_barred is False
    assert a.total_owed_inr == fresh.ruling.compensation_inr
    assert to_dict(a)["incidents"][0]["time_barred"] in (True, False)


def test_old_incident_stays_out_of_the_demand_table():
    a = _audit_with_old_and_fresh()
    pack = generate_complaint_pack(a, "Test", "0000", "t@example.com")
    assert "444455556666" in pack.split("## Older incidents")[0]
    assert "111122223333" in pack.split("## Older incidents")[1]


def test_disclaimer_present_in_every_pack():
    a = _audit_with_old_and_fresh()
    pack = generate_complaint_pack(a, "Test", "0000", "t@example.com")
    assert "not legal advice" in pack


def test_fresh_only_audit_has_no_older_incidents_section():
    txns = _failed_pair(date(2026, 6, 1), date(2026, 6, 20), "444455556666")
    a = build_audit(txns, as_of=AS_OF)
    pack = generate_complaint_pack(a, "Test", "0000", "t@example.com")
    assert "Older incidents" not in pack
