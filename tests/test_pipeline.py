"""The end-to-end exam: parser + reconciler graded against planted ground truth."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from refundradar.audit import audit_csv_text, build_audit, to_dict
from refundradar.complaint import generate_complaint_pack
from refundradar.parser import parse_generic_csv, parse_generic_csv_text
from refundradar.reconcile import EXCLUDED, LATE, NEVER, ON_TIME, reconcile

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
AS_OF = date(2026, 7, 23)


@pytest.fixture(scope="module")
def txns():
    return parse_generic_csv(SAMPLES / "demo_statement.csv")


@pytest.fixture(scope="module")
def truth():
    return json.loads((SAMPLES / "ground_truth.json").read_text())


def _by_ref(incidents):
    return {i.txn.ref: i for i in incidents}


def test_parser_reads_every_row(txns):
    assert len(txns) == 229
    assert all(t.amount > 0 for t in txns)


def test_parser_prefers_explicit_ref_column(txns):
    atm = [t for t in txns if t.is_debit and t.channel == "atm" and t.ref]
    assert atm, "planted ATM incident must carry the Ref column value"


def test_reconciler_passes_the_exam(txns, truth):
    incidents = _by_ref(reconcile(txns, as_of=AS_OF))
    expected = {i["ref"]: i for i in truth["incidents"]}

    for ref, exp in expected.items():
        if not exp["is_incident"]:
            assert incidents[ref].status == EXCLUDED, "fell for the trap!"
        elif exp["refund_date"] is None:
            assert ref not in incidents, (
                "a never-reversed failure is invisible in the statement alone "
                "(D6) — flagging it without user confirmation would be a guess"
            )
        elif exp["days_late"] == 0:
            assert incidents[ref].status == ON_TIME
        else:
            assert incidents[ref].status == LATE
            assert incidents[ref].ruling.days_late == exp["days_late"]
            assert incidents[ref].ruling.compensation_inr == exp["compensation_inr"]

    flagged_late = [i for i in incidents.values() if i.status in (LATE, NEVER)]
    assert len(flagged_late) == 2, "precision: nothing but planted incidents flagged"


def test_confirmed_never_refunded_is_claimed(txns, truth):
    unref = next(i for i in truth["incidents"] if i["refund_date"] is None)
    incidents = _by_ref(reconcile(txns, {unref["ref"]}, as_of=AS_OF))
    inc = incidents[unref["ref"]]
    assert inc.status == NEVER
    days = (AS_OF - date(2026, 6, 16)).days
    assert inc.ruling.days_late == days
    assert inc.ruling.compensation_inr == days * 100


def test_audit_totals(txns, truth):
    unref = next(i for i in truth["incidents"] if i["refund_date"] is None)
    a = build_audit(txns, {unref["ref"]}, as_of=AS_OF)
    accrued = (AS_OF - date(2026, 6, 16)).days * 100
    assert a.total_owed_inr == 800 + 600 + accrued
    assert a.stuck_amount == Decimal(2499)
    assert a.on_time_count == 1
    d = to_dict(a)
    assert d["total_owed_inr"] == a.total_owed_inr
    assert len(d["incidents"]) == len(a.incidents)


def test_complaint_pack_contents(txns, truth):
    unref = next(i for i in truth["incidents"] if i["refund_date"] is None)
    a = build_audit(txns, {unref["ref"]}, as_of=AS_OF)
    pack = generate_complaint_pack(a, "Dhanush Jangadi", "1234", "test@example.com")
    assert "RBI/2019-20/67" in pack
    assert f"Rs.{a.total_owed_inr}" in pack
    assert "suo moto" in pack
    assert "cms.rbi.org.in" in pack
    import re
    evidence_rows = re.findall(r"^\| \d+ \|", pack, flags=re.MULTILINE)
    assert len(evidence_rows) == 3, "3 claimable rows in the evidence table"
    assert "MYNTRA" not in pack, "the genuine refund must never enter a legal letter"


def test_audit_csv_text_matches_file_path(txns):
    text = (SAMPLES / "demo_statement.csv").read_text(encoding="utf-8-sig")
    a1 = audit_csv_text(text, as_of=AS_OF)
    a2 = build_audit(txns, as_of=AS_OF)
    assert to_dict(a1) == to_dict(a2)


def test_bad_format_raises_clear_error():
    with pytest.raises(ValueError, match="Unrecognized statement format"):
        parse_generic_csv_text("foo,bar\n1,2\n")
