"""Canonical transaction model — every bank parser normalizes into this.

A statement line from any bank becomes a Transaction; detect_channel() maps
the bank's narration jargon onto rules/rbi_tat.yaml channel codes so the
rules engine knows which deadline applies.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Recognized here but NOT evaluable by the rules engine: separate
# penal-interest regime, deferred (rules/DECISIONS.md, D2).
UNSUPPORTED_CHANNELS = {"neft", "rtgs"}

# Merchant-side UPI markers: QR codes and payment-gateway VPAs.
_MERCHANT_VPA = re.compile(r"QR|RAZORPAY|\.RZP|BHARATPE|EAZYPAY|PAYU|BILLDESK")
# Person-side UPI markers: literal P2P tag, or a phone-number VPA (digits@).
_PERSON_VPA = re.compile(r"\bP2P\b|\b\d{7,}@")
# ATM needs word boundaries: "PAYTM" contains "ATM".
_ATM = re.compile(r"\bATM\b|\bATW\b|\bNWD\b|\bEAW\b|CASH WDL|CSH WDL")
_NACH = re.compile(r"\bNACH\b|\bECS\b|\bACH\b")

_RRN = re.compile(r"\b\d{12}\b")                 # UPI/IMPS retrieval ref number
_UTR16 = re.compile(r"\b[A-Z]{4}[A-Z0-9]{12}\b")  # NEFT-style 16-char UTR


@dataclass
class Transaction:
    """One statement line, normalized. Money is Decimal — never float."""

    txn_date: date
    amount: Decimal            # always positive; direction lives in is_debit
    is_debit: bool
    narration: str             # raw statement description, untouched
    ref: str | None = None     # UTR/RRN if one could be extracted
    channel: str | None = None  # rbi_tat.yaml code, or neft/rtgs, or None
    balance: Decimal | None = None
    bank: str = ""
    alt_ref: str | None = None  # a second reference on the same line, also matched


def detect_channel(narration: str) -> str | None:
    """Map a statement narration to a channel code, or None if unknown.

    UPI subtype is a judgment call (DECISIONS.md, D5): person markers
    upgrade to upi_p2p (T+1); anything ambiguous stays upi_p2m (T+5),
    the reading least favorable to the claim and hardest to dispute.
    """
    n = narration.upper()
    if "UPI" in n:
        if _PERSON_VPA.search(n) and not _MERCHANT_VPA.search(n):
            return "upi_p2p"
        return "upi_p2m"
    if "IMPS" in n:
        return "imps"
    if "NEFT" in n:
        return "neft"
    if "RTGS" in n:
        return "rtgs"
    if "AEPS" in n or "AADHAAR PAY" in n:
        return "aeps"
    if "APBS" in n:
        return "apbs"
    if _ATM.search(n):
        return "atm"
    if "ECOM" in n or "E-COM" in n:
        return "ecom"
    if re.search(r"\bPOS\b", n):
        return "pos"
    if _NACH.search(n):
        return "nach"
    if "CARD TO CARD" in n:
        return "card_to_card"
    return None


def extract_ref(narration: str) -> str | None:
    """Pull the UTR/RRN out of a narration, if present.

    12-digit RRN (UPI/IMPS) first, then 16-char alphanumeric UTR (NEFT).
    Heuristic by nature: masked card numbers (512967XX1234) never match,
    but any stray 12-digit run would — Phase 2 matching treats refs as
    strong hints, not proof.
    """
    m = _RRN.search(narration) or _UTR16.search(narration.upper())
    return m.group(0) if m else None


def make_transaction(
    txn_date: date,
    amount,
    is_debit: bool,
    narration: str,
    *,
    balance=None,
    bank: str = "",
) -> Transaction:
    """Build a Transaction with channel and ref auto-detected.

    Amounts pass through Decimal(str(...)) so float inputs can't smuggle
    in binary rounding errors.
    """
    return Transaction(
        txn_date=txn_date,
        amount=Decimal(str(amount)),
        is_debit=is_debit,
        narration=narration,
        ref=extract_ref(narration),
        channel=detect_channel(narration),
        balance=None if balance is None else Decimal(str(balance)),
        bank=bank,
    )
