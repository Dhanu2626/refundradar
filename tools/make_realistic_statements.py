"""Write samples/realistic/: synthetic statements laid out the way SBI's and
HDFC's own downloads are, for testing the readers end to end.

Every name, account number, reference and amount is made up, and every file
says so in its first line. The layouts follow what the banks publish and what
the 2026-07-24 SBI field test saw (DECISIONS.md, D10 and D16): HDFC NetBanking's
Excel download with its customer block, asterisk rules, STATEMENT SUMMARY and
footer; its Delimited text download; the same Excel file saved as CSV in an
Indian-locale Excel (1,23,456.00); SBI's account statement with its account
block, "Balance as on" and footer, as OnlineSBI heads it (Txn Date ... Branch
Code) and as the field-tested download did (Date / Details); and SBI's
password-protected download (msoffcrypto's agile encryption, as SBI's is).

They are not copies of any real statement, so they test the readers against
the layouts as known, not against a layout nobody has seen yet: a real export
is still the only proof of that.

The planted cases, audited as of 1 Sep 2026 (tests/test_realistic_statements.py):
  HDFC  UPI reversed next day under the same reference (on time); a BigBasket
        UPI reversed 9 days later (4 days late: Rs.400 owed); an ATM withdrawal
        reversed as REVERSAL-ATW (on time) beside its identical twin (not);
        an NWD withdrawal credited back as REV-NWD, a wording the engine does
        not know, so it asks; a Myntra order refund (a genuine refund, not a
        failure); home-loan ACH debits and a DMart card payment printed with
        no reference; NEFT, IMPS, charges and interest.
  SBI   UPI reversed under a fresh UPI/REF reference, on time and 3 days
        late (asked, never assumed); an ATM withdrawal and a card payment
        with no reference; NEFT salary, IMPS, charges and interest.

    pip install xlwt   # only to write the .xls
    python tools/make_realistic_statements.py
The SBI download's password is 54321150690: SBI's scheme (the last five digits
of the registered mobile number, then the date of birth as DDMMYY) with made-up
values.
"""

import csv
import io
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "realistic"
SBI_PASSWORD = "54321150690"
LABEL = "SYNTHETIC TEST STATEMENT - NOT ISSUED BY ANY BANK - ALL DATA MADE UP"

D = Decimal

# --- HDFC -------------------------------------------------------------------

HDFC_OPENING = D("62418.35")
# (date, narration, Chq./Ref.No., withdrawal, deposit)
HDFC_ROWS = [
    (date(2026, 6, 1), "NEFT CR-CITI0100000-ACME TECHNOLOGIES PVT LTD-SAMPLE CUSTOMER-CITIN26060112345",
     "CITIN26060112345", None, "85000.00"),
    (date(2026, 6, 2), "ACH D- TP ACH HDFC LTD-HL0000123456", "0000000000000000", "24350.00", None),
    (date(2026, 6, 3), "UPI-SWIGGY-SWIGGY.STORES@AXB-UTIB0000100-615412345601-UPI",
     "0000615412345601", "486.00", None),
    (date(2026, 6, 4), "UPI-SWIGGY-SWIGGY.STORES@AXB-UTIB0000100-615412345601-REVERSAL",
     "0000615412345601", None, "486.00"),
    (date(2026, 6, 5), "POS 416021XXXXXX4321 AMAZON PAY INDIA PRIVA POS DEBIT", "0000615512345602",
     "1349.00", None),
    (date(2026, 6, 7), "ATW-416021XXXXXX4321-S1ANHY23-HYDERABAD", "0000615812340002", "10000.00", None),
    (date(2026, 6, 9), "IMPS-616012345603-SAMPLE FRIEND-SBIN-XXXXXXX9876-DINNER", "0000616012345603",
     "1200.00", None),
    (date(2026, 6, 9), ".IMPS P2A CHARGES 616012345603 INCL GST", "0000616012345603", "5.90", None),
    (date(2026, 6, 10), "UPI-IRCTC-IRCTCWEBUPI@SBI-SBIN0016209-616112345604-TICKET",
     "0000616112345604", "2345.00", None),
    (date(2026, 6, 12), "NWD-416021XXXXXX4321-SPCNE123-HYDERABAD", "0000616312340005", "5000.00", None),
    (date(2026, 6, 15), "BIL/ONL/000123456789/TSSPDCL/SAMPLE", "0000616612345606", "1436.00", None),
    (date(2026, 6, 17), "REV-NWD-416021XXXXXX4321-SPCNE123-HYDERABAD", "0000616312340005", None, "5000.00"),
    (date(2026, 6, 18), "UPI-MYNTRA-MYNTRA@ICICI-ICIC0DC0099-616912345607-ORDER", "0000616912345607",
     "1799.00", None),
    (date(2026, 6, 20), "UPI-MYNTRA-MYNTRA@ICICI-ICIC0DC0099-616912345607-REFUND ORDER RETURN",
     "0000616912345607", None, "1799.00"),
    (date(2026, 6, 22), "CHQ DEP - MICR CTS - HYDERABAD - 000123", "0000000000000123", None, "3000.00"),
    (date(2026, 6, 25), "UPI-JIO-JIOPREPAID@PAYTM-PYTM0123456-617612345608-RECHARGE", "0000617612345608",
     "349.00", None),
    (date(2026, 6, 28), "POS 416021XXXXXX4321 DMART HYDERABAD", "0000000000000000", "2187.40", None),
    (date(2026, 6, 30), "INTEREST PAID TILL 30-JUN-2026", "0000000000000000", None, "402.00"),
    (date(2026, 7, 1), "NEFT CR-CITI0100000-ACME TECHNOLOGIES PVT LTD-SAMPLE CUSTOMER-CITIN26070112345",
     "CITIN26070112345", None, "85000.00"),
    (date(2026, 7, 2), "ACH D- TP ACH HDFC LTD-HL0000123456", "0000000000000000", "24350.00", None),
    (date(2026, 7, 4), "UPI-ZOMATO-ZOMATO@HDFCBANK-HDFC0000499-618512345609-ORDER", "0000618512345609",
     "612.00", None),
    (date(2026, 7, 6), "UPI-BIGBASKET-BIGBASKET@ICICI-ICIC0DC0099-618712345610-ORDER", "0000618712345610",
     "3245.00", None),
    (date(2026, 7, 8), "IMPS-618912345611-SAMPLE LANDLORD-ICIC-XXXXXXXX5566-RENT JUL", "0000618912345611",
     "18000.00", None),
    (date(2026, 7, 10), "ATW-416021XXXXXX4321-S1ANHY23-HYDERABAD", "0000619112340012", "3000.00", None),
    (date(2026, 7, 10), "ATW-416021XXXXXX4321-S1ANHY23-HYDERABAD", "0000619112340013", "3000.00", None),
    (date(2026, 7, 12), "REVERSAL-ATW-416021XXXXXX4321-S1ANHY23-HYDERABAD", "0000619112340012", None, "3000.00"),
    (date(2026, 7, 15), "UPI-BIGBASKET-BIGBASKET@ICICI-ICIC0DC0099-618712345610-REVERSAL",
     "0000618712345610", None, "3245.00"),
    (date(2026, 7, 16), "UPI-AMAZON-AMAZONUPI@APL-UTIB0000553-619712345614-PAY", "0000619712345614",
     "1149.00", None),
    (date(2026, 7, 18), "NEFT DR-SBIN0000999-SAMPLE RELATIVE-NETBANK, MUM-N199262615", "N199262615",
     "10000.00", None),
    (date(2026, 7, 24), "POS 416021XXXXXX4321 PVR CINEMAS HYDERABAD", "0000620512345616", "860.00", None),
    (date(2026, 7, 25), "CASH DEPOSIT BY - SELF - HYDERABAD", "0000000000000000", None, "5000.00"),
    (date(2026, 8, 1), "NEFT CR-CITI0100000-ACME TECHNOLOGIES PVT LTD-SAMPLE CUSTOMER-CITIN26080112345",
     "CITIN26080112345", None, "85000.00"),
    (date(2026, 8, 2), "ACH D- TP ACH HDFC LTD-HL0000123456", "0000000000000000", "24350.00", None),
    (date(2026, 8, 3), "UPI-SWIGGY-SWIGGY.STORES@AXB-UTIB0000100-621512345617-UPI", "0000621512345617",
     "520.00", None),
    (date(2026, 8, 5), "UPI-PAYTM-PAYTMQR5550001@PAYTM-PYTM0123456-621712345618-GROCERIES",
     "0000621712345618", "1500.00", None),
    (date(2026, 8, 10), "DC ANNUAL FEE 416021XXXXXX4321 INCL GST", "0000000000000000", "590.00", None),
    (date(2026, 8, 16), "UPI-MAKEMYTRIP-MMT@ICICI-ICIC0DC0099-622812345619-FLIGHT", "0000622812345619",
     "6850.00", None),
    (date(2026, 8, 17), "UPI-MAKEMYTRIP-MMT@ICICI-ICIC0DC0099-622812345619-REVERSAL FAILED TXN",
     "0000622812345619", None, "6850.00"),
    (date(2026, 8, 24), "UPI-SAMPLE FRIEND-9000000002@OKICICI-ICIC0000000-623612345620-DINNER SPLIT",
     "0000623612345620", None, "650.00"),
    (date(2026, 8, 31), "SMS CHARGES FOR QTR ENDED JUN 2026 INCL GST", "0000000000000000", "17.70", None),
]


def _hdfc_ledger():
    balance, rows = HDFC_OPENING, []
    for day, text, ref, out, inn in HDFC_ROWS:
        balance += D(inn or 0) - D(out or 0)
        rows.append((day, text, ref, D(out) if out else None, D(inn) if inn else None, balance))
    return rows


def _ddmmyy(day: date) -> str:
    return f"{day:%d/%m/%y}"


def _indian(value: Decimal) -> str:
    """1,23,456.00: what Excel writes in an Indian locale."""
    whole, paise = f"{value:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups + [tail]) + "." + paise


def hdfc_sheet() -> list[list]:
    """The NetBanking Excel download, cell by cell (numbers as numbers)."""
    ledger = _hdfc_ledger()
    stars = ["*" * 16] * 7
    sheet = [
        ["HDFC BANK Ltd.", "", "", "", "Page No .:  1", "", "Statement of accounts"],
        [LABEL],
        ["MR. SAMPLE CUSTOMER", "", "", "", "Account Branch :", "SAMPLE BRANCH"],
        ["FLAT 1 SAMPLE APARTMENTS", "", "", "", "Address :", "1 SAMPLE ROAD"],
        ["SAMPLE COLONY", "", "", "", "City :", "HYDERABAD 500000"],
        ["HYDERABAD 500000", "", "", "", "State :", "TELANGANA"],
        ["TELANGANA INDIA", "", "", "", "Phone no. :", "XXXXXXXXXX"],
        ["", "", "", "", "OD Limit :", "0.00", "Currency :  INR"],
        ["JOINT HOLDERS :", "", "", "", "Email :", "XXXXXXXX@EXAMPLE.COM"],
        ["", "", "", "", "Cust ID :", "XXXXXXXX"],
        ["", "", "", "", "Account No :", "XXXXXXXXXX2626", "SAVINGS - SYNTHETIC"],
        ["", "", "", "", "A/C Open Date :", "01/01/20"],
        ["Nomination : Registered", "", "", "", "Account Status :", "Regular"],
        ["Statement From : 01/06/2026", "", "To : 31/08/2026", "", "RTGS/NEFT IFSC :", "HDFC0XXXXXX",
         "MICR : XXXXXXXXX"],
        ["", "", "", "", "Branch Code :", "XXXX", "Product Code :  XXX"],
        stars,
        ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
        stars,
    ]
    for day, text, ref, out, inn, bal in ledger:
        sheet.append([_ddmmyy(day), text, ref, _ddmmyy(day), float(out) if out else "",
                      float(inn) if inn else "", float(bal)])
    debits = [r for r in ledger if r[3]]
    credits = [r for r in ledger if r[4]]
    sheet += [
        stars,
        ["STATEMENT SUMMARY  :-"],
        [],
        ["Opening Balance", "", "Dr Count", "Cr Count", "Debits", "Credits", "Closing Bal"],
        [float(HDFC_OPENING), "", len(debits), len(credits), float(sum(r[3] for r in debits)),
         float(sum(r[4] for r in credits)), float(ledger[-1][5])],
        [],
        ["Generated On: 01/09/26 09:15:32", "", "Generated By: XXXXXXXX", "", "Requesting Branch Code: NET"],
        ["This is a computer generated statement and does not require signature."],
        [LABEL],
    ]
    return sheet


def hdfc_csv() -> str:
    """The Excel download saved as CSV by an Indian-locale Excel."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    for row in hdfc_sheet():
        w.writerow([_indian(D(str(c))) if isinstance(c, float) else c for c in row])
    return out.getvalue()


def hdfc_delimited() -> str:
    """The Delimited download: the table only, every field space-padded."""
    ledger = _hdfc_ledger()
    width = max(len(r[1]) for r in ledger) + 1
    lines = [" Date     ," + "Narration".ljust(width) + ",Value Dat,Debit Amount       ,"
             "Credit Amount      ,Chq/Ref Number   ,Closing Balance"]
    for day, text, ref, out, inn, bal in ledger:
        lines.append(f" {_ddmmyy(day)} ,{text.ljust(width)},{_ddmmyy(day)} ,{out or D(0):>17.2f}  ,"
                     f"{inn or D(0):>17.2f}  ,{ref:<16} ,{bal:>15.2f}")
    return "\r\n".join(lines) + "\r\n"


# --- SBI --------------------------------------------------------------------

SBI_OPENING = D("48215.60")
# (date, description, Ref No./Cheque No., debit, credit)
SBI_ROWS = [
    (date(2026, 6, 1), "DEP TFR NEFT*HDFC0000001*N152600012345*ACME TECHNOLOGIES PVT LTD",
     "TRANSFER FROM 3199XXXXXX01", None, "72000.00"),
    (date(2026, 6, 2), "WDL TFR UPI/DR/615312340001/SAMPLE LANDLORD/HDFC/9000000001@okhdfc/Rent Jun",
     "TRANSFER TO 4897XXXXXX01", "16000.00", None),
    (date(2026, 6, 4), "WDL TFR UPI/DR/615512340002/SWIGGY/YESB/swiggy@yesb/UPI", "TRANSFER TO 4897XXXXXX02",
     "412.00", None),
    (date(2026, 6, 6), "DEP TFR UPI/REF/615799990002/CR", "TRANSFER FROM 4897XXXXXX03", None, "412.00"),
    (date(2026, 6, 9), "ATM WDL ATM CASH 3591 AMEERPET HYDERABAD", "-", "6000.00", None),
    (date(2026, 6, 12), "WDL TFR UPI/DR/616312340004/AMAZON/UTIB/amazonupi@apl/Pay", "TRANSFER TO 4897XXXXXX04",
     "2899.00", None),
    (date(2026, 6, 20), "DEP TFR UPI/REF/617199990004/CR", "TRANSFER FROM 4897XXXXXX05", None, "2899.00"),
    (date(2026, 6, 23), "POS 416021XXXXXX4321 RELIANCE SMART HYDERABAD", "-", "1675.30", None),
    (date(2026, 6, 30), "CREDIT INTEREST", "-", None, "311.00"),
    (date(2026, 7, 1), "DEP TFR NEFT*HDFC0000001*N182600012345*ACME TECHNOLOGIES PVT LTD",
     "TRANSFER FROM 3199XXXXXX01", None, "72000.00"),
    (date(2026, 7, 2), "WDL TFR UPI/DR/618312340006/SAMPLE LANDLORD/HDFC/9000000001@okhdfc/Rent Jul",
     "TRANSFER TO 4897XXXXXX06", "16000.00", None),
    (date(2026, 7, 7), "WDL TFR INB IMPS/P2A/618812340007/SAMPLE FRIEND/HDFC/xxxx9876/Trip",
     "TRANSFER TO 4897XXXXXX07", "2500.00", None),
    (date(2026, 7, 11), "WDL TFR UPI/DR/619212340008/IRCTC/SBIN/irctcwebupi@sbi/Ticket",
     "TRANSFER TO 4897XXXXXX08", "1840.00", None),
    (date(2026, 7, 19), "DEBIT-ATMCard AMC 416021*4321 Classic", "-", "236.00", None),
    (date(2026, 7, 26), "DEP TFR UPI/CR/620712340009/SAMPLE FRIEND/HDFC/9000000002@okhdfc/Share",
     "TRANSFER FROM 4897XXXXXX09", None, "1250.00"),
    (date(2026, 8, 1), "DEP TFR NEFT*HDFC0000001*N213600012345*ACME TECHNOLOGIES PVT LTD",
     "TRANSFER FROM 3199XXXXXX01", None, "72000.00"),
    (date(2026, 8, 2), "WDL TFR UPI/DR/621412340010/SAMPLE LANDLORD/HDFC/9000000001@okhdfc/Rent Aug",
     "TRANSFER TO 4897XXXXXX10", "16000.00", None),
    (date(2026, 8, 8), "WDL TFR UPI/DR/622012340011/ELECTRICITY BOARD/SBIN/tsspdcl@sbi/Bill",
     "TRANSFER TO 4897XXXXXX11", "1318.00", None),
    (date(2026, 8, 14), "ATM WDL ATM CASH 3591 AMEERPET HYDERABAD", "-", "4000.00", None),
    (date(2026, 8, 25), "SMS CHARGES FOR:01-04-2026 TO 30-06-2026", "-", "17.70", None),
]


def _sbi_ledger():
    balance, rows = SBI_OPENING, []
    for day, text, ref, out, inn in SBI_ROWS:
        balance += D(inn or 0) - D(out or 0)
        rows.append((day, text, ref, D(out) if out else None, D(inn) if inn else None, balance))
    return rows


def _money(value) -> str:
    return f"{value:,.2f}"


def sbi_sheet(yono: bool = False) -> list[list]:
    """SBI's account statement. OnlineSBI heads the table Txn Date / Value Date /
    Description / Ref No./Cheque No. / Branch Code; the download field-tested in
    July said Date / Details, with no value date or branch code."""
    ledger = _sbi_ledger()
    sheet = [
        [LABEL],
        ["Account Name", ":", "MR SAMPLE CUSTOMER"],
        ["Address", ":", "FLAT 1 SAMPLE APARTMENTS, SAMPLE COLONY, HYDERABAD-500000"],
        ["Date", ":", "1 Sep 2026"],
        ["Account Number", ":", "XXXXXXX2626"],
        ["Account Description", ":", "REGULAR SB CHQ-INDIVIDUALS"],
        ["Branch", ":", "SAMPLE BRANCH"],
        ["Drawing Power", ":", "0.00"],
        ["Interest Rate(% p.a.)", ":", "2.5"],
        ["MOD Balance", ":", "0.00"],
        ["CIF No.", ":", "XXXXXXXX1234"],
        ["CKYCR Number", ":", "XXXXXXXXXXXXXX"],
        ["IFS Code (Indian Financial System)", ":", "SBIN0XXXXXX"],
        ["MICR Code (Magnetic Ink Character Recognition)", ":", "XXXXXXXXX"],
        ["Nomination Registered", ":", "Yes"],
        ["Balance as on 1 Jun 2026", ":", _money(SBI_OPENING)],
        [],
        ["Account Statement from 1 Jun 2026 to 31 Aug 2026"],
        [],
    ]
    if yono:
        sheet.append(["Date", "Details", "Ref No./Cheque No.", "Debit", "Credit", "Balance"])
        for day, text, ref, out, inn, bal in ledger:  # a spreadsheet's own dates and numbers
            sheet.append([datetime(day.year, day.month, day.day), text, ref,
                          float(out) if out else None, float(inn) if inn else None, float(bal)])
    else:
        sheet.append(["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Branch Code",
                      "Debit", "Credit", "Balance"])
        for day, text, ref, out, inn, bal in ledger:  # text, as OnlineSBI writes it
            when = f"{day.day} {day:%b %Y}"
            sheet.append([when, when, text, ref, "99999", _money(out) if out else " ",
                          _money(inn) if inn else " ", _money(bal)])
    sheet += [
        [],
        ["**This is a computer generated statement and does not require a signature."],
        ["Please do not share your ATM, Debit/Credit card number, PIN and OTP with anyone. "
         "Bank never asks for such information."],
        [LABEL],
    ]
    return sheet


# --- writing ----------------------------------------------------------------

def _xlsx(rows: list[list]) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)
    wb.properties.creator = "RefundRadar synthetic sample"
    wb.properties.created = wb.properties.modified = datetime(2026, 9, 1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _xls(rows: list[list]) -> bytes:
    import xlwt
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v != "":
                ws.write(r, c, v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _locked(data: bytes) -> bytes:
    from msoffcrypto.format.ooxml import OOXMLFile
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(data)).encrypt(SBI_PASSWORD, out)
    return out.getvalue()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sbi = _xlsx(sbi_sheet())
    files = {
        "hdfc_netbanking.xls": _xls(hdfc_sheet()),
        "hdfc_netbanking_saved_as.csv": hdfc_csv().encode("utf-8"),
        "hdfc_delimited.txt": hdfc_delimited().encode("utf-8"),
        "sbi_account_statement.xlsx": sbi,
        "sbi_account_statement_locked.xlsx": _locked(sbi),
        "sbi_details_layout.xlsx": _xlsx(sbi_sheet(yono=True)),
    }
    for name, data in files.items():
        (OUT / name).write_bytes(data)
        print(f"wrote samples/realistic/{name} ({len(data):,} bytes)")


if __name__ == "__main__":
    sys.exit(main())
