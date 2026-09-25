"""Pairing rules every bank shares (synthetic data). Per-defect replays are
in test_regressions.py; adversarial scenarios in test_adversarial.py."""

from datetime import date

import pytest

from refundradar.model import make_transaction
from refundradar.reconcile import (CONFIRM, EXCLUDED, LATE, NEVER, ON_TIME,
                                   _language, reconcile)

AS_OF = date(2026, 4, 30)
FAILED_P2P = "UPI/DR/604112345678/9876543210@OKHDFC/RENT"  # T+1


def _txn(day, amount, is_debit, narration, month=2):
    return make_transaction(date(2026, month, day), amount, is_debit, narration)


@pytest.mark.parametrize("narration, reading", [
    ("UPI/CR/1/REV OF FAILED TXN", "reversal"),
    ("ATM REV CR-1-CASH NOT DISPENSED", "reversal"),
    ("DEP TFR UPI/REF/616903000009/CR", "reversal"),
    ("IMPS-1-RETURNED TO SENDER", "reversal"),         # the phrase, not the word RETURN
    ("UPI/CR/1/MYNTRA REFUND ORDER RETURN", "refund"),
    ("CASHBACK CREDIT", "refund"),
    ("UPI/CR/1/REFUND OF FAILED TXN", "ambiguous"),    # refund and failure together
    ("UPI/REFUND/1/MYNTRA", "ambiguous"),              # contains SBI's UPI/REF marker
    ("IMPS-1-RETURN", "ambiguous"),                    # returned order, or returned payment?
    ("UPI/CR/1/RAVI KUMAR", "ambiguous"),
])
def test_wording_is_only_a_verdict_when_it_points_one_way(narration, reading):
    assert _language(narration) == reading


def test_a_credit_tied_by_reference_is_not_paired_again():
    txns = [_txn(10, "2000", True, "UPI/DR/604112345678/PAYTMQR1@PAYTM/X"),
            _txn(12, "2000", True, "UPI/DR/604399990000/9876543210@OKHDFC/Y"),
            _txn(13, "2000", False, "UPI/CR/604112345678/REV OF FAILED TXN")]
    assert [(i.status, i.txn.ref) for i in reconcile(txns, as_of=AS_OF)] == [
        (ON_TIME, "604112345678")]
    # nor handed to a payment the user says failed: that one was never refunded
    assert [(i.status, i.txn.ref) for i in reconcile(txns, {"604399990000"}, as_of=AS_OF)] == [
        (ON_TIME, "604112345678"), (NEVER, "604399990000")]


def test_a_rows_second_reference_ties_it_to_its_reversal():
    reversal = _txn(23, "2000", False, "REVERSAL 605399998888")
    reversal.alt_ref = "604112345678"
    [inc] = reconcile([_txn(10, "2000", True, "UPI/DR/604112345678/PAYTMQR1@PAYTM/X"),
                       reversal], as_of=AS_OF)
    assert inc.status == LATE


def test_plain_merchant_refund_is_still_excluded():
    [inc] = reconcile([_txn(16, "1299", True, "UPI/DR/604712345678/MYNTRA.PAYU@AXIS/ORDER"),
                       _txn(26, "1299", False, "UPI/CR/604712345678/MYNTRA REFUND ORDER RETURN")],
                      as_of=AS_OF)
    assert inc.status == EXCLUDED


def test_answering_an_inferred_pairing_claims_it_late():
    # the UI flow: the fallback asks to confirm the pairing, the user
    # clicks "Yes, it failed", and the audit re-runs with that reference
    txns = [_txn(10, "2000", True, "UPI/DR/604112345678/PAYTMQR1@PAYTM/GROCERIES"),
            _txn(19, "2000", False, "UPI/REF/605300001111/CR")]
    [asked] = reconcile(txns, as_of=AS_OF)
    assert asked.status == CONFIRM
    [answered] = reconcile(txns, {asked.txn.ref}, as_of=AS_OF)
    assert answered.status == LATE
    assert answered.refund_date == asked.refund_date


def test_confirmed_failure_takes_its_only_later_reversal_even_far_away():
    # 23 days: beyond the fallback window, but the only same-amount credit
    # after a payment the user says failed. Claimed only up to that date.
    [inc] = reconcile([_txn(10, "2000", True, FAILED_P2P),
                       _txn(5, "2000", False, "UPI/REF/605300001111/CR", month=3)],
                      {"604112345678"}, as_of=AS_OF)
    assert (inc.status, inc.refund_date) == (LATE, date(2026, 3, 5))
    assert inc.ruling.compensation_inr == 2200  # due 11 Feb, back 5 Mar


def test_confirmed_failure_with_no_later_credit_is_never_refunded():
    [inc] = reconcile([_txn(10, "2000", True, FAILED_P2P),
                       _txn(9, "2000", False, "UPI/REF/605300001111/CR")],  # before it
                      {"604112345678"}, as_of=AS_OF)
    assert inc.status == NEVER
