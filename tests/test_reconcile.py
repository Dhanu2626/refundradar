"""Pairing rules every bank shares: one credit per debit, mixed wording,
and confirmed failures refunded under a fresh reference (synthetic data)."""

from datetime import date

import pytest

from refundradar.model import make_transaction
from refundradar.reconcile import CONFIRM, EXCLUDED, LATE, NEVER, ON_TIME, reconcile

AS_OF = date(2026, 4, 30)
FAILED_P2P = "UPI/DR/604112345678/9876543210@OKHDFC/RENT"  # T+1


def _txn(day, amount, is_debit, narration, month=2):
    return make_transaction(date(2026, month, day), amount, is_debit, narration)


def test_duplicated_debit_row_is_claimed_once():
    debit = "UPI/DR/604112345678/PAYTMQR1@PAYTM/GROCERIES"
    incs = reconcile([_txn(10, "2000", True, debit), _txn(10, "2000", True, debit),
                      _txn(23, "2000", False, "UPI/CR/604112345678/REV OF FAILED TXN")],
                     as_of=AS_OF)
    assert [i.status for i in incs] == [LATE]  # was two Rs.800 claims


def test_reused_reference_goes_to_the_closest_earlier_debit():
    # two instalments share a mandate reference; the reversal is the later one's
    emi = "ACH D- LOAN-604100000001"
    incs = reconcile([_txn(1, "2000", True, emi), _txn(20, "2000", True, emi),
                      _txn(21, "2000", False, emi + "-REVERSAL")], as_of=AS_OF)
    assert [(i.status, i.txn.txn_date.day) for i in incs] == [(ON_TIME, 20)]
    # was a Rs.1,900 "late" claim against the instalment that went through


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


@pytest.mark.parametrize("wording", ["IMPS-604112345678-RETURNED TO SENDER",
                                     "UPI/CR/604112345678/REFUND OF FAILED TXN"])
def test_wording_that_says_refund_and_failure_asks_the_user(wording):
    txns = [_txn(10, "2000", True, "IMPS-604112345678-RAVI KUMAR-RENT"),
            _txn(23, "2000", False, wording)]
    [inc] = reconcile(txns, as_of=AS_OF)
    assert inc.status == CONFIRM  # was excluded as a returned order (D11)
    [inc] = reconcile(txns, {"604112345678"}, as_of=AS_OF)
    assert inc.status == LATE  # "Yes, it failed" makes it a reversal


def test_plain_merchant_refund_is_still_excluded():
    [inc] = reconcile([_txn(16, "1299", True, "UPI/DR/604712345678/MYNTRA.PAYU@AXIS/ORDER"),
                       _txn(26, "1299", False, "UPI/CR/604712345678/MYNTRA REFUND ORDER RETURN")],
                      as_of=AS_OF)
    assert inc.status == EXCLUDED


def test_confirmed_failure_refunded_under_fresh_reference_is_late_not_never():
    # Before D12 this claimed "never refunded": Rs.7,800 accruing to the
    # audit date for money that came back on day 2.
    [inc] = reconcile([_txn(10, "2000", True, FAILED_P2P),
                       _txn(12, "2000", False, "UPI/REF/605300001111/CR")],
                      {"604112345678"}, as_of=AS_OF)
    assert inc.status == LATE
    assert inc.refund_date == date(2026, 2, 12)
    assert inc.ruling.compensation_inr == 100


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


def test_confirmed_failure_with_only_a_distant_reversal_is_not_claimed():
    [inc] = reconcile([_txn(10, "2000", True, FAILED_P2P),
                       _txn(5, "2000", False, "UPI/REF/605300001111/CR", month=3)],
                      {"604112345678"}, as_of=AS_OF)
    assert inc.status == CONFIRM
    assert inc.ruling is None


def test_confirmed_failure_with_no_reversal_is_still_never_refunded():
    [inc] = reconcile([_txn(10, "2000", True, FAILED_P2P)], {"604112345678"}, as_of=AS_OF)
    assert inc.status == NEVER
