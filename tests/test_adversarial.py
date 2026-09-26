"""Adversarial scenarios. The audit may ask, or stay silent, but it must never
claim more than the bank actually owes in the scenario's story (synthetic)."""

from datetime import date

import pytest

from refundradar.model import make_transaction
from refundradar.parser import parse_hdfc_rows
from refundradar.reconcile import CONFIRM, EXCLUDED, LATE, NEVER, ON_TIME, reconcile
from refundradar.rules_engine import evaluate

AS_OF = date(2026, 4, 30)
REF = "604112345678"
P2M = f"UPI/DR/{REF}/PAYTMQR1@PAYTM/GROCERIES"      # UPI to a merchant, due T+5
P2P = f"UPI/DR/{REF}/9876543210@OKHDFC/RENT"         # UPI to a person, due T+1
IMPS = f"IMPS-{REF}-RAVI KUMAR-RENT"                 # due T+1
EMI = "ACH D- LOAN-604100000001"                     # NACH, due T+1
SAME_REF_REVERSAL = f"UPI/CR/{REF}/REV OF FAILED TXN"
NEW_REF_REVERSAL = "UPI/REF/605300001111/CR"


def d(day, month=2):
    return date(2026, month, day)


def txn(day, amount, is_debit, narration, month=2):
    return make_transaction(d(day, month), amount, is_debit, narration)


def owed(channel, paid, refunded=None):
    return evaluate(channel, paid, refunded, as_of=AS_OF).compensation_inr


def hdfc_late_refund(narration, ref_cell):
    header = ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.",
              "Deposit Amt.", "Closing Balance"]
    return parse_hdfc_rows([
        header,
        ["10/02/26", f"UPI-PAYTM-PAYTMQR1@PAYTM-PYTM0123456-{REF}-GROCERIES",
         f"0000{REF}", "10/02/26", "2,000.00", "", "10,000.00"],
        ["23/02/26", narration, ref_cell, "23/02/26", "", "2,000.00", "12,000.00"],
    ])


PAYTM_TWICE = [txn(10, "2000", True, P2M), txn(10, "2000", True, P2M),
               txn(23, "2000", False, SAME_REF_REVERSAL)]
NEW_REF_9_DAYS = [txn(10, "2000", True, P2M), txn(19, "2000", False, NEW_REF_REVERSAL)]
NEW_REF_28_DAYS = [txn(10, "2000", True, P2M), txn(10, "2000", False, NEW_REF_REVERSAL, month=3)]
BARE_RETURN = [txn(10, "2000", True, IMPS), txn(23, "2000", False, f"IMPS-{REF}-RETURN")]

SCENARIOS = [
    # transactions, refs the user confirmed failed, expected verdicts,
    # and what the bank really owes in this scenario's story
    pytest.param(PAYTM_TWICE, set(), [CONFIRM], owed("upi_p2m", d(10), d(23)),
                 id="duplicate payment"),
    pytest.param(PAYTM_TWICE, {REF}, [LATE, CONFIRM], owed("upi_p2m", d(10), d(23)),
                 id="duplicate payment, confirmed"),
    pytest.param([txn(10, "2000", True, P2M), txn(23, "2000", False, SAME_REF_REVERSAL),
                  txn(23, "2000", False, SAME_REF_REVERSAL)],
                 set(), [LATE], owed("upi_p2m", d(10), d(23)), id="duplicate refund"),
    pytest.param([txn(1, "2000", True, EMI), txn(20, "2000", True, EMI),
                  txn(1, "2000", False, EMI + "-REVERSAL", month=3)],
                 set(), [CONFIRM], owed("nach", d(20), d(1, 3)),
                 id="reference reused across payments"),
    pytest.param(NEW_REF_9_DAYS, set(), [CONFIRM], owed("upi_p2m", d(10), d(19)),
                 id="refund under a new reference"),
    pytest.param(NEW_REF_9_DAYS, {REF}, [LATE], owed("upi_p2m", d(10), d(19)),
                 id="refund under a new reference, confirmed"),
    pytest.param(NEW_REF_28_DAYS, set(), [CONFIRM], owed("upi_p2m", d(10), d(10, 3)),
                 id="refund under a new reference 28 days later"),
    pytest.param(NEW_REF_28_DAYS, {REF}, [LATE], owed("upi_p2m", d(10), d(10, 3)),
                 id="refund under a new reference 28 days later, confirmed"),
    pytest.param(hdfc_late_refund("REVERSAL-UPI-PAYTM-GROCERIES", f"00{REF}"), set(),
                 [LATE], owed("upi_p2m", d(10), d(23)), id="refund with a padded reference"),
    pytest.param(hdfc_late_refund("REVERSAL-UPI-605399998888-GROCERIES", f"0000{REF}"), set(),
                 [LATE], owed("upi_p2m", d(10), d(23)),
                 id="refund with another number in its narration"),
    pytest.param([txn(10, "2000", True, P2M), txn(12, "2000", False, SAME_REF_REVERSAL)],
                 set(), [ON_TIME], 0, id="failed payment refunded on time"),
    pytest.param([txn(10, "2000", True, P2P),
                  txn(12, "2000", False, "UPI/CR/605300001111/RAVI KUMAR")],
                 {REF}, [CONFIRM], owed("upi_p2p", d(10), d(12)),
                 id="failed payment refunded in plain wording, confirmed"),
    pytest.param([txn(10, "2000", True, P2P)], set(), [], owed("upi_p2p", d(10)),
                 id="failed payment never refunded"),
    pytest.param([txn(10, "2000", True, P2P)], {REF}, [NEVER], owed("upi_p2p", d(10)),
                 id="failed payment never refunded, confirmed"),
    pytest.param([txn(16, "1299", True, "UPI/DR/604712345678/MYNTRA.PAYU@AXIS/ORDER"),
                  txn(26, "1299", False, "UPI/CR/604712345678/MYNTRA REFUND ORDER RETURN")],
                 set(), [EXCLUDED], 0, id="genuine shop refund"),
    pytest.param([txn(10, "2000", True, P2M)], set(), [], 0, id="genuine payment, no refund"),
    pytest.param(BARE_RETURN, set(), [CONFIRM], owed("imps", d(10), d(23)), id="bare RETURN"),
    pytest.param(BARE_RETURN, {REF}, [LATE], owed("imps", d(10), d(23)),
                 id="bare RETURN, confirmed"),
    pytest.param([txn(1, "500", True, "UPI/DR/600000000001/PAYTMQR1@PAYTM/A"),
                  txn(3, "500", True, "UPI/DR/600000000002/PAYTMQR2@PAYTM/B"),
                  txn(4, "500", False, "UPI/REF/690000000001/CR"),   # refunds A, on time
                  txn(9, "500", False, "UPI/REF/690000000002/CR")],  # refunds B, a day late
                 {"600000000001", "600000000002"}, [CONFIRM, CONFIRM],
                 owed("upi_p2m", d(1), d(4)) + owed("upi_p2m", d(3), d(9)),
                 id="two confirmed failures, two new-reference refunds"),
    pytest.param([txn(10, "2000", True, P2P),
                  txn(20, "2000", False, "UPI/CR/605399990000/FRIEND REPAYS", month=3)],
                 {REF}, [CONFIRM], owed("upi_p2p", d(10)),
                 id="confirmed failure, unrelated same-amount credit later"),
]


@pytest.mark.parametrize("txns, confirmed, verdicts, truly_owed", SCENARIOS)
def test_never_claims_more_than_is_owed(txns, confirmed, verdicts, truly_owed):
    incidents = reconcile(txns, confirmed, as_of=AS_OF)
    assert [i.status for i in incidents] == verdicts
    claimed = sum(i.ruling.compensation_inr for i in incidents if i.status in (LATE, NEVER))
    assert claimed <= truly_owed
    # one verdict per payment, and every claim carries the ruling behind it
    assert len({id(i.txn) for i in incidents}) == len(incidents)
    assert all(i.ruling is not None for i in incidents if i.status in (LATE, NEVER))
