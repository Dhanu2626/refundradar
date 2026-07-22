"""Channel detection and ref extraction against realistic narration formats."""

from datetime import date
from decimal import Decimal

import pytest

from refundradar.model import detect_channel, extract_ref, make_transaction

# (narration, expected channel) — formats modeled on HDFC/SBI/ICICI statements
CHANNEL_CASES = [
    # UPI person-to-person: phone-number VPA or explicit P2P tag
    ("UPI/DR/519912345678/RAMESH KUMAR/OKHDFC/9876543210@OKHDFC/PAID", "upi_p2p"),
    ("TO TRANSFER-UPI/DR/521234567890/9123456789@YBL/RENT", "upi_p2p"),
    # UPI merchant: QR / gateway VPAs, or ambiguous (D5: default to p2m)
    ("UPI/DR/520099887766/PAYTMQR2810050501@PAYTM/GROCERIES", "upi_p2m"),
    ("UPI-SWIGGY-SWIGGY.JUICE@ICICI-ICIC0DC0099-520011223344-ORDER", "upi_p2m"),
    ("UPI/DR/522211334455/RAZORPAY.COURSE@HDFCBANK/FEES", "upi_p2m"),
    # IMPS
    ("IMPS-P2A-519920123456-ANJALI-HDFC-XXXX3456", "imps"),
    # NEFT/RTGS: recognized but a different regime (D2)
    ("NEFT DR-BARB0KIMXXX-LANDLORD-HDFCN12345678901-RENT JULY", "neft"),
    ("RTGS/UTIB0000001/SUPPLIER ADVANCE", "rtgs"),
    # ATM: ATW/NWD codes, and the PAYTM trap must NOT match "ATM"
    ("ATW-512967XX1234-S1CN262626-HYDERABAD", "atm"),
    ("NWD-512967XX1234-SBI ATM-SECUNDERABAD", "atm"),
    ("EAW-512967XX1234-CASH WDL-BEGUMPET", "atm"),
    # Cards
    ("ECOM PUR/AMAZON PAY INDIA/512967XX1234", "ecom"),
    ("POS 512967XX1234 RATNADEEP SUPER MKT", "pos"),
    # Mandates / Aadhaar rails
    ("ACH-DR-TP BAJAJ FINANCE-EMI 07/26", "nach"),
    ("AEPS/CW/262626/CSC KIOSK MEDCHAL", "aeps"),
    # Not a payment-system transaction
    ("CHQ PAID 000123 SELF", None),
]


@pytest.mark.parametrize("narration,expected", CHANNEL_CASES)
def test_detect_channel(narration, expected):
    assert detect_channel(narration) == expected


def test_paytm_is_upi_not_atm():
    # "PAYTM" contains the letters ATM — word boundaries must protect us
    assert detect_channel("UPI/DR/520055667788/MERCHANT@PAYTM/LUNCH") == "upi_p2m"


def test_extract_rrn_12_digit():
    assert extract_ref("UPI/DR/519912345678/X@Y/NOTE") == "519912345678"


def test_extract_neft_utr():
    assert extract_ref("NEFT DR-HDFCN12345678901-RENT") == "HDFCN12345678901"


def test_masked_card_is_not_a_ref():
    assert extract_ref("POS 512967XX1234 RATNADEEP") is None


def test_make_transaction_decimal_and_detection():
    t = make_transaction(
        date(2026, 7, 21), 2499.50, True,
        "UPI/DR/519912345678/9876543210@OKHDFC/PAID",
        bank="HDFC",
    )
    assert t.amount == Decimal("2499.50")
    assert isinstance(t.amount, Decimal)
    assert t.channel == "upi_p2p"
    assert t.ref == "519912345678"
    assert t.is_debit is True
