"""Write samples/sbi_statement.xlsx: a synthetic statement in SBI's export layout.

Every name, number and amount is made up. The rows plant the cases an SBI
audit meets, with SBI's own habits: debits read WDL TFR, credits DEP TFR, and
a failed UPI payment comes back as DEP TFR UPI/REF under a fresh reference
(DECISIONS.md, D9). Audited as of 1 Sep 2026 (tests/test_sbi.py):

  3 Jun   Rs.450 Swiggy, reversed 5 Jun            on time (matched by amount and date)
  8 Jun   Rs.2,000 Myntra, reversed 16 Jun         looks 3 days late: asked, never assumed
  14 Jun  Rs.5,000 ATM cash, no reference          offered to confirm by its row
  25 Jun  Rs.1,845.50 card payment, no reference   offered to confirm by its row
  2 Jul   Rs.1,299 IRCTC, then two Rs.1,299 UPI/REF credits (20 and 28 Jul):
          neither can be tied to it on its own; confirming it asks which one
  5-8 Jul two Rs.350 Zomato payments, one reversal on time (the closer one)
  22 Jul  Rs.780 BookMyShow, never reversed        a failure only you can confirm

The balances run from Rs.42,000 and add up, as SBI's must (D16).

    python tools/make_sbi_sample.py
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "samples" / "sbi_statement.xlsx"
OPENING = Decimal("42000.00")
BRANCH = "09999"

# (date, description, ref, debit, credit)
ROWS = [
    (date(2026, 6, 1), "DEP TFR NEFT*HDFC0000001*N152600012345*ACME TECH PVT LTD",
     "N152600012345", None, "55000.00"),
    (date(2026, 6, 3), "WDL TFR UPI/DR/615412340001/SWIGGY/YESB/swiggy.order@yesb/Payment",
     "-", "450.00", None),
    (date(2026, 6, 5), "DEP TFR UPI/REF/615499990001/CR", "-", None, "450.00"),
    (date(2026, 6, 8), "WDL TFR UPI/DR/615912340002/MYNTRA/ICIC/myntra@icici/Payment",
     "-", "2000.00", None),
    (date(2026, 6, 10), "WDL TFR UPI/DR/616112340003/SAMPLE LANDLORD/SBIN/9000000001@ybl/Rent",
     "-", "15000.00", None),
    (date(2026, 6, 14), "ATM WDL-ATM CASH 9999 AMEERPET HYDERABAD", "-", "5000.00", None),
    (date(2026, 6, 16), "DEP TFR UPI/REF/616799990002/CR", "-", None, "2000.00"),
    (date(2026, 6, 20), "DEP TFR UPI/CR/617112340004/SAMPLE FRIEND/SBIN/9000000002@ybl/Dinner",
     "-", None, "1200.00"),
    (date(2026, 6, 25), "POS 416021XXXXXX4321 DMART HYDERABAD", "-", "1845.50", None),
    (date(2026, 7, 1), "DEP TFR NEFT*HDFC0000001*N182600012345*ACME TECH PVT LTD",
     "N182600012345", None, "55000.00"),
    (date(2026, 7, 2), "WDL TFR UPI/DR/618312340005/IRCTC/HDFC/irctc@hdfcbank/Payment",
     "-", "1299.00", None),
    (date(2026, 7, 5), "WDL TFR UPI/DR/618612340006/ZOMATO/HDFC/zomato@hdfcbank/Payment",
     "-", "350.00", None),
    (date(2026, 7, 6), "WDL TFR UPI/DR/618712340007/ZOMATO/HDFC/zomato@hdfcbank/Payment",
     "-", "350.00", None),
    (date(2026, 7, 8), "DEP TFR UPI/REF/618999990007/CR", "-", None, "350.00"),
    (date(2026, 7, 20), "DEP TFR UPI/REF/620199990008/CR", "-", None, "1299.00"),
    (date(2026, 7, 22), "WDL TFR UPI/DR/620312340010/BOOKMYSHOW/ICIC/bms@icici/Payment",
     "-", "780.00", None),
    (date(2026, 7, 28), "DEP TFR UPI/REF/620999990009/CR", "-", None, "1299.00"),
    (date(2026, 8, 1), "DEP TFR NEFT*HDFC0000001*N213600012345*ACME TECH PVT LTD",
     "N213600012345", None, "55000.00"),
    (date(2026, 8, 5), "WDL TFR UPI/DR/621712340011/ELECTRICITY BOARD/SBIN/tsspdcl@sbi/Bill",
     "-", "1120.00", None),
    (date(2026, 8, 10), "ATM WDL-ATM CASH 9999 KUKATPALLY HYDERABAD", "-", "2000.00", None),
]


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def rows() -> list[list]:
    sheet = [
        ["Account Name", ":", "MR SAMPLE CUSTOMER"],
        ["Address", ":", "SYNTHETIC SAMPLE, HYDERABAD"],
        ["Account Number", ":", "XXXXXXXX2626"],
        ["Account Description", ":", "SAVINGS ACCOUNT (SYNTHETIC SAMPLE)"],
        ["IFS Code", ":", "SBIN0XXXXXX"],
        [f"Balance as on 1 Jun 2026", ":", _money(OPENING)],
        [],
        ["Account Statement from 1 Jun 2026 to 31 Aug 2026"],
        [],
        ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Branch Code",
         "Debit", "Credit", "Balance"],
    ]
    balance = OPENING
    for day, text, ref, debit, credit in ROWS:
        balance += Decimal(credit or 0) - Decimal(debit or 0)
        when = f"{day.day} {day:%b %Y}"
        sheet.append([when, when, text, ref, BRANCH,
                      _money(Decimal(debit)) if debit else "",
                      _money(Decimal(credit)) if credit else "", _money(balance)])
    sheet += [[], ["**This is a computer generated statement and does not require a signature."]]
    return sheet


def main() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Statement"
    for row in rows():
        ws.append(row)
    wb.properties.creator = "RefundRadar synthetic sample"
    wb.properties.created = wb.properties.modified = datetime(2026, 9, 1)
    wb.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
