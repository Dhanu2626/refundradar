"""One regression test per defect found reviewing HDFC support (#1-#17).

Each test replays the input that exposed the defect and asserts the safe
outcome. Every one fails on commit fd6b890, where the defects were found,
and fails again if its fix is reverted; PR #1 carries the evidence matrix.
Only APIs that existed at fd6b890 are used, so the replay is fair.
Synthetic data only.
"""

from datetime import date

import pytest

from refundradar.model import make_transaction
from refundradar.parser import parse_hdfc_rows
from refundradar.reconcile import CONFIRM, LATE, NEVER, ON_TIME, reconcile

AS_OF = date(2026, 4, 30)
HEADER = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.",
          "Deposit Amt.", "Closing Balance"]


def _row(day, narration, ref="", withdrawal="", deposit="", balance=""):
    return [day, narration, ref, day, withdrawal, deposit, balance]


PAYMENT = _row("03/02/26", "UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-PAY",
               "0000603412345678", withdrawal="450.00", balance="39,550.00")
REVERSAL = "UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-REVERSAL"


def _refusal(*rows) -> str:
    with pytest.raises(ValueError) as err:
        parse_hdfc_rows([HEADER, *rows])
    return str(err.value)


def _txn(day, amount, is_debit, narration, month=2):
    return make_transaction(date(2026, month, day), amount, is_debit, narration)


def _owed(incidents) -> int:
    return sum(i.ruling.compensation_inr for i in incidents if i.status in (LATE, NEVER))


# --- HDFC parsing: a row that can't be read safely stops the audit ----------

def test_defect_01_unrecognised_date_stops_the_audit():
    # was: the reversal row vanished without a word
    msg = _refusal(PAYMENT, _row("05-02-26", REVERSAL, deposit="450.00", balance="40,000.00"))
    assert msg.startswith("Row 3, Date:") and "'05-02-26'" in msg
    # an unambiguous timestamp is read, not refused
    txns = parse_hdfc_rows([HEADER, PAYMENT, _row("05/02/26 10:15", REVERSAL, "0000603412345678",
                                                 deposit="450.00", balance="40,000.00")])
    assert [t.txn_date for t in txns] == [date(2026, 2, 3), date(2026, 2, 5)]


def test_defect_02_amount_with_text_stops_the_audit():
    # was: "450.00 Cr" read as blank, so the refund row vanished
    msg = _refusal(PAYMENT, _row("05/02/26", REVERSAL, deposit="450.00 Cr", balance="40,000.00"))
    assert msg.startswith("Row 3, Deposit Amt.:") and "'450.00 Cr'" in msg


def test_defect_03_both_amounts_filled_stops_the_audit():
    # was: recorded as a Rs.10 debit; the Rs.450 deposit disappeared
    msg = _refusal(PAYMENT, _row("05/02/26", REVERSAL, withdrawal="10.00", deposit="450.00",
                                 balance="40,440.00"))
    assert msg.startswith("Row 3:")
    assert "Withdrawal Amt. (10.00)" in msg and "Deposit Amt. (450.00)" in msg


def test_defect_04_negative_amount_stops_the_audit():
    # was: a -450.00 transaction that could never match its refund
    msg = _refusal(_row("03/02/26", PAYMENT[1], PAYMENT[2], withdrawal="-450.00",
                        balance="39,550.00"))
    assert msg.startswith("Row 2, Withdrawal Amt.:") and "'-450.00'" in msg


def test_defect_05_blank_date_on_a_money_row_stops_the_audit():
    # was: the row vanished
    msg = _refusal(PAYMENT, _row("", REVERSAL, deposit="450.00", balance="40,000.00"))
    assert msg.startswith("Row 3, Date:") and "found ''" in msg


def test_defect_06_amount_in_the_wrong_column_stops_the_audit():
    # was: a dated row whose 450.00 sat under Value Dt was passed over as
    # "no money"
    moved = _row("05/02/26", REVERSAL, balance="40,000.00")
    moved[3] = "450.00"
    msg = _refusal(PAYMENT, moved)
    assert msg.startswith("Row 3, Value Dt:") and "'450.00'" in msg
    # without balances to cross-check, it still isn't passed over
    msg = _refusal(PAYMENT[:6] + [""], moved[:6] + [""])
    assert msg.startswith("Row 3, Value Dt:")


def test_defect_07_duplicated_row_stops_the_audit():
    # was: both copies accepted, so the payment existed twice
    msg = _refusal(PAYMENT, PAYMENT)
    assert msg.startswith("Row 3, Closing Balance:")
    assert "39,550.00" in msg and "39,100.00" in msg


def test_defect_08_rows_after_the_summary_stop_the_audit():
    # was: nothing after the first STATEMENT SUMMARY was ever read
    reversal = _row("05/02/26", REVERSAL, deposit="450.00", balance="40,000.00")
    summary = ["STATEMENT SUMMARY  :-"]
    assert _refusal(PAYMENT, summary, HEADER, reversal).startswith(
        "Row 4: another statement's header")
    assert _refusal(PAYMENT, summary, reversal).startswith("Row 4: a dated row with an amount")


def test_defect_09_totals_that_lost_their_label_never_become_a_transaction():
    # was: a Rs.450 debit dated 6 Jul 2009, read from the totals row
    labels = ["Opening Balance", "", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"]
    totals = [40000.0, "", 1, 0, 450.0, 0.0, 39550.0]  # 40000.0 = Excel serial 6 Jul 2009
    assert _refusal(PAYMENT, labels, totals).startswith("Row 3, Date:")
    msg = _refusal(PAYMENT, totals)
    assert "Closing Balance" in msg and "row 3" in msg.lower()


# --- References: a late refund quoting the original anywhere is found ------

def _late_refund(narration, ref_cell):
    return reconcile(parse_hdfc_rows([
        HEADER,
        _row("10/02/26", "UPI-PAYTM-PAYTMQR1@PAYTM-PYTM0123456-604112345678-GROCERIES",
             "0000604112345678", withdrawal="2,000.00", balance="10,000.00"),
        # 13 days later: past the T+5 deadline and the 10-day fallback window
        _row("23/02/26", narration, ref_cell, deposit="2,000.00", balance="12,000.00"),
    ]), as_of=AS_OF)


def test_defect_10_reference_padded_to_another_width_still_matches():
    # was: 00604112345678 never equalled 604112345678; Rs.800 missed
    [inc] = _late_refund("REVERSAL-UPI-PAYTM-GROCERIES", "00604112345678")
    assert (inc.status, inc.ruling.compensation_inr) == (LATE, 800)


def test_defect_11_fresh_number_in_narration_does_not_hide_the_original():
    # was: the narration's 605399998888 won; the column's original was ignored
    [inc] = _late_refund("REVERSAL-UPI-605399998888-GROCERIES", "0000604112345678")
    assert (inc.status, inc.ruling.compensation_inr) == (LATE, 800)


def test_defect_12_text_token_in_narration_does_not_hide_the_original():
    # was: PAYTMQR28100505X was taken for a UTR; the column was ignored
    [inc] = _late_refund("REVERSAL-UPI-PAYTMQR28100505X-GROCERIES", "0000604112345678")
    assert (inc.status, inc.ruling.compensation_inr) == (LATE, 800)


# --- Matching: never claim more than the statement proves ------------------

PAYTM = "UPI/DR/604112345678/PAYTMQR1@PAYTM/GROCERIES"


def test_defect_13_duplicated_payment_is_never_claimed_twice():
    txns = [_txn(10, "2000", True, PAYTM), _txn(10, "2000", True, PAYTM),
            _txn(23, "2000", False, "UPI/CR/604112345678/REV OF FAILED TXN")]
    # was: two Rs.800 claims. A reference on two rows can't say which failed,
    # so it asks first,
    assert [i.status for i in reconcile(txns, as_of=AS_OF)] == [CONFIRM]
    # and once confirmed it claims once, with no "never refunded" for the copy
    confirmed = reconcile(txns, {"604112345678"}, as_of=AS_OF)
    assert _owed(confirmed) == 800
    assert NEVER not in {i.status for i in confirmed}


def test_defect_14_reused_reference_creates_no_false_claim():
    emi = "ACH D- LOAN-604100000001"
    # was: the Feb 21 reversal went to the Feb 1 instalment, a Rs.1,900 claim
    incs = reconcile([_txn(1, "2000", True, emi), _txn(20, "2000", True, emi),
                      _txn(21, "2000", False, emi + "-REVERSAL")], as_of=AS_OF)
    assert [(i.status, i.txn.txn_date.day) for i in incs] == [(ON_TIME, 20)]
    # a late reversal on a shared reference proves nothing by itself
    incs = reconcile([_txn(1, "2000", True, emi), _txn(20, "2000", True, emi),
                      _txn(28, "2000", False, emi + "-REVERSAL")], as_of=AS_OF)
    assert [i.status for i in incs] == [CONFIRM] and _owed(incs) == 0


def test_defect_15_returned_to_sender_is_a_reversal():
    # was: RETURN matched first, so it was excluded as a merchant refund
    [inc] = reconcile([_txn(10, "2000", True, "IMPS-604112345678-RAVI KUMAR-RENT"),
                       _txn(23, "2000", False, "IMPS-604112345678-RETURNED TO SENDER")],
                      as_of=AS_OF)
    assert (inc.status, inc.ruling.compensation_inr) == (LATE, 1200)


def test_defect_16_refund_of_failed_txn_asks_instead_of_excluding():
    txns = [_txn(10, "2000", True, "IMPS-604112345678-RAVI KUMAR-RENT"),
            _txn(23, "2000", False, "UPI/CR/604112345678/REFUND OF FAILED TXN")]
    # was: excluded as a merchant refund, silently
    assert [i.status for i in reconcile(txns, as_of=AS_OF)] == [CONFIRM]
    # "Yes, it failed" settles it
    assert [i.status for i in reconcile(txns, {"604112345678"}, as_of=AS_OF)] == [LATE]


def test_defect_17_confirmed_failure_refunded_under_new_reference_is_not_never_refunded():
    # was: "never refunded", Rs.7,800 accruing, for money back on day 2
    [inc] = reconcile([_txn(10, "2000", True, "UPI/DR/604112345678/9876543210@OKHDFC/RENT"),
                       _txn(12, "2000", False, "UPI/REF/605300001111/CR")],
                      {"604112345678"}, as_of=AS_OF)
    assert (inc.status, inc.ruling.compensation_inr, inc.refund_date) == (
        LATE, 100, date(2026, 2, 12))
