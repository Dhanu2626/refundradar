"""The circular's annex, verified case by case.

Every test is a real-life scenario phrased in dates: if these pass, the
rulebook file and the engine agree with RBI/2019-20/67.
"""

from datetime import date

import pytest

from refundradar.rules_engine import evaluate, load_rules

T = date(2026, 7, 1)  # transaction day in all scenarios below


def test_upi_p2p_refunded_on_time_owes_nothing():
    r = evaluate("upi_p2p", T, refund_date=date(2026, 7, 2))  # T+1, the deadline
    assert r.on_time
    assert r.compensation_inr == 0


def test_upi_p2p_refunded_ten_days_past_deadline_owes_1000():
    r = evaluate("upi_p2p", T, refund_date=date(2026, 7, 12))  # deadline was Jul 2
    assert not r.on_time
    assert r.days_late == 10
    assert r.compensation_inr == 1000


def test_atm_has_t_plus_5_deadline():
    r = evaluate("atm", T, refund_date=date(2026, 7, 6))  # exactly T+5
    assert r.on_time
    assert r.compensation_inr == 0


def test_atm_two_days_late_owes_200():
    r = evaluate("atm", T, refund_date=date(2026, 7, 8))
    assert r.days_late == 2
    assert r.compensation_inr == 200


def test_never_refunded_accrues_until_as_of_date():
    r = evaluate("upi_p2p", T, refund_date=None, as_of=date(2026, 8, 1))
    assert not r.refunded
    assert r.days_late == 30  # deadline Jul 2 -> Aug 1
    assert r.compensation_inr == 3000


def test_upi_p2m_gets_the_longer_merchant_deadline():
    # Same refund date, but P2M's T+5 deadline makes it on time where P2P wouldn't be
    r = evaluate("upi_p2m", T, refund_date=date(2026, 7, 5))
    assert r.on_time


def test_unknown_channel_fails_loudly():
    with pytest.raises(KeyError, match="Known channels"):
        evaluate("carrier_pigeon", T, refund_date=None, as_of=T)


def test_ruling_cites_the_circular():
    r = evaluate("imps", T, refund_date=date(2026, 7, 10))
    assert "RBI/2019-20/67" in r.citation
    assert "T+1" in r.citation


def test_rulebook_covers_all_annex_channels():
    rules = load_rules()
    expected = {"atm", "card_to_card", "pos", "ecom", "imps", "upi_p2p",
                "upi_p2m", "aeps", "apbs", "nach", "ppi_on_us"}
    assert expected <= set(rules["by_code"])
