"""Synthetic statement generator — ground truth for grading the reconciler.

Writes a realistic 6-month statement (generic CSV export format) with
failure incidents planted at known places, plus an answer key. Phase 2's
reconciliation engine is measured against that key: precision and recall,
not "seems to work".
"""

import csv
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from refundradar.rules_engine import evaluate

CSV_HEADER = ["Date", "Narration", "Ref", "Debit", "Credit", "Balance"]

_MERCHANT_VPAS = [
    "SWIGGY.ORDER@ICICI", "ZOMATO.PAY@HDFCBANK", "PAYTMQR2810050501@PAYTM",
    "RATNADEEP.RZP@AXIS", "JIO.RECHARGE@SBI", "AMAZONPAY@APL",
]
_PERSON_VPAS = ["9876543210@OKHDFC", "9123456789@YBL", "9988776655@AXL"]


def _rrn(rng: random.Random) -> str:
    return str(rng.randrange(10**11, 10**12))


def _money(rng: random.Random, lo: int, hi: int) -> Decimal:
    return Decimal(rng.randrange(lo, hi))


def generate(seed: int = 26, days: int = 180, start: date = date(2026, 1, 1)):
    """Return (rows, ground_truth). Deterministic for a given seed."""
    rng = random.Random(seed)
    events: list[tuple[date, str, str, Decimal | None, Decimal | None]] = []

    def debit(d, narration, ref, amt):
        events.append((d, narration, ref, amt, None))

    def credit(d, narration, ref, amt):
        events.append((d, narration, ref, None, amt))

    for offset in range(days):
        d = start + timedelta(days=offset)
        if d.day == 1:
            credit(d, "NEFT CR-ACME TECH PVT LTD-SALARY", f"ACMEN{_rrn(rng)}0001", Decimal(52000))
        if d.day == 5:
            debit(d, "ACH-DR-TP BAJAJ FINANCE-EMI", "", Decimal(4500))
        for _ in range(rng.randrange(0, 3)):
            vpa = rng.choice(_MERCHANT_VPAS if rng.random() < 0.8 else _PERSON_VPAS)
            debit(d, f"UPI/DR/{_rrn(rng)}/{vpa}/PAYMENT", "", _money(rng, 40, 1200))
        if offset % 12 == 0:
            debit(d, f"ATW-512967XX1234-S1CN{100000 + offset}-HYDERABAD", "", _money(rng, 20, 40) * 100)

    incidents = []

    def plant(day_offset, channel, amount, narr_debit, narr_credit, refund_after, is_incident, note):
        d = start + timedelta(days=day_offset)
        ref = _rrn(rng)
        debit(d, narr_debit.format(ref=ref), ref, amount)
        refund_date = None
        if refund_after is not None:
            refund_date = d + timedelta(days=refund_after)
            credit(refund_date, narr_credit.format(ref=ref), ref, amount)
        entry = {
            "ref": ref, "channel": channel, "amount": str(amount),
            "txn_date": d.isoformat(),
            "refund_date": refund_date.isoformat() if refund_date else None,
            "is_incident": is_incident, "note": note,
            "days_late": None, "compensation_inr": None,
        }
        if is_incident and refund_date is not None:
            ruling = evaluate(channel, d, refund_date)
            entry["days_late"] = ruling.days_late
            entry["compensation_inr"] = ruling.compensation_inr
        incidents.append(entry)

    plant(20, "upi_p2m", Decimal(750),
          "UPI/DR/{ref}/SWIGGY.ORDER@ICICI/FAILED PAYMENT",
          "UPI/CR/{ref}/REV OF FAILED TXN", 3, True,
          "failed UPI merchant payment, refunded on time (T+5)")
    plant(45, "upi_p2m", Decimal(2000),
          "UPI/DR/{ref}/PAYTMQR2810050501@PAYTM/GROCERIES",
          "UPI/CR/{ref}/REV OF FAILED TXN", 13, True,
          "failed UPI merchant payment, refunded 8 days late -> Rs.800")
    plant(70, "atm", Decimal(5000),
          "ATW-512967XX1234-S1CN{ref}-BEGUMPET",
          "ATM REV CR-{ref}-CASH NOT DISPENSED", 11, True,
          "ATM cash-not-dispensed, refunded 6 days late -> Rs.600")
    plant(165, "upi_p2p", Decimal(2499),
          "UPI/DR/{ref}/9876543210@OKHDFC/TRANSFER",
          "", None, True,
          "failed UPI P2P, never refunded — compensation accruing daily")
    plant(95, "upi_p2m", Decimal(1299),
          "UPI/DR/{ref}/MYNTRA.PAYU@AXIS/ORDER 8817",
          "UPI/CR/{ref}/MYNTRA REFUND ORDER RETURN", 10, False,
          "TRAP: genuine merchant refund for a returned order — NOT a failed "
          "transaction; a ref-only matcher would wrongly claim Rs.500 here")

    events.sort(key=lambda e: e[0])
    balance = Decimal(40000)
    rows = []
    for d, narration, ref, dr, cr in events:
        balance = balance - dr if dr is not None else balance + cr
        rows.append({
            "Date": d.strftime("%d-%m-%Y"), "Narration": narration, "Ref": ref,
            "Debit": f"{dr:.2f}" if dr is not None else "",
            "Credit": f"{cr:.2f}" if cr is not None else "",
            "Balance": f"{balance:.2f}",
        })

    ground_truth = {
        "seed": seed, "start": start.isoformat(), "days": days,
        "incidents": incidents,
    }
    return rows, ground_truth


def write(out_dir: Path, seed: int = 26) -> None:
    rows, truth = generate(seed=seed)
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "demo_statement.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)
    with open(out_dir / "ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=2)


if __name__ == "__main__":
    samples = Path(__file__).resolve().parent.parent / "samples"
    write(samples)
    rows, truth = generate()
    planted = sum(1 for i in truth["incidents"] if i["is_incident"])
    print(f"Wrote {len(rows)} rows to {samples / 'demo_statement.csv'}")
    print(f"Planted {planted} real incidents + 1 trap; answer key in ground_truth.json")
