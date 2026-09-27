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

The PDFs are drawn the way statement PDFs are: descriptions and references
that wrap onto two or three lines (at spaces, or mid-word when a word is too
long for its column), a header that wraps, the page header repeated on every
page, page numbers in the footer, right-aligned Indian-format amounts, grid
lines (SBI) or none (HDFC), HDFC's STATEMENT SUMMARY, and SBI's download locked
with AES-256.

It also draws samples/pdf_layouts/ (LAYOUTS): the same statements drawn the ways
other report writers draw a table, and PDFs the reader must refuse.

    pip install xlwt reportlab pypdf pillow   # only to write the .xls and the PDFs
    python tools/make_realistic_statements.py
The SBI downloads' password is 54321150690: SBI's scheme (the last five digits
of the registered mobile number, then the date of birth as DDMMYY) with made-up
values.
"""

import csv
import io
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "realistic"
LAYOUT_DIR = ROOT / "samples" / "pdf_layouts"
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


# --- PDF --------------------------------------------------------------------

# printed at the foot of every page of HDFC's statement
HDFC_FOOTER = [
    "HDFC BANK LIMITED",
    "*Closing balance includes funds earmarked for hold and uncleared funds",
    "Contents of this statement will be considered correct if no error is reported within 30 days of "
    "receipt of statement.",
    "State account branch GSTN: XXXXXXXXXXXXXXX   Registered Office Address: SAMPLE ADDRESS, MUMBAI 400000",
]


def _wrap(text: str, width: float, font: str, size: float, mode: str = "word") -> list[str]:
    """Lines of `text` no wider than `width`, broken the way report writers do:
    "word" at spaces, and inside a word only when the word alone is wider than
    the column; "hyphen" also after a hyphen or slash; "chars" anywhere."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    fits = lambda t: stringWidth(t, font, size) <= width
    if mode == "chars":  # break-all: every line filled, a space at a break dropped
        lines, line = [], ""
        for ch in text:
            if fits(line + ch):
                line += ch
                continue
            lines.append(line.rstrip())
            line = "" if ch == " " else ch
        return lines + ([line] if line else [])
    parts = []  # (piece, what joins it to the next: a space, or nothing after - and /)
    for word in text.split(" "):
        bits = (re.findall(r"[^/-]*[/-]|[^/-]+$", word) or [word]) if mode == "hyphen" else [word]
        parts += [(bit, "" if k < len(bits) - 1 else " ") for k, bit in enumerate(bits)]
    lines, line, joiner = [], "", ""
    for piece, after in parts:
        if fits(line + joiner + piece if line else piece):
            line = line + joiner + piece if line else piece
        else:
            if line:
                lines.append(line)
            while not fits(piece):  # too long for any line: break it where the column ends
                cut = max(i for i in range(1, len(piece) + 1) if fits(piece[:i]))
                lines.append(piece[:cut])
                piece = piece[cut:]
            line = piece
        joiner = after
    return lines + ([line] if line else [])


def _pdf(page_top, header, widths, rows, closing, *, grid, right_from, wrap="word",
         repeat_heading=True, split_rows=False, align="top", heading_align="top",
         apart=False, font="Helvetica", size=7.3, bold_twice=False, footer=(),
         note_after=None, row_after_closing=None) -> bytes:
    """A statement PDF: `page_top(canvas, page)` draws each page's head and
    says where the table starts; then the table, its heading on every page;
    then the `closing` lines; a footer and "Page N of M" on every page.

    The keywords draw the same statement the ways other report writers do:
    how cells wrap, a heading on the first page only, a row split by a page
    break, cells centred or bottom-aligned in their row, each word drawn on
    its own (no space characters), another font, a heading drawn twice as
    fake bold. And two a reader must stop at: a note set apart between two
    rows (`note_after`: the row it follows), a transaction drawn in the
    table's columns after the closing lines (`row_after_closing`).
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as rl

    bold = {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[font]
    left, lead, head_size = 36, round(size * 1.26, 2), size + 0.3
    bottom = 58 + 9 * len(footer)
    xs = [left + sum(widths[:i]) for i in range(len(widths) + 1)]
    drop = {"top": 0, "middle": 0.5, "bottom": 1}[align]

    def draw(total):
        buf = io.BytesIO()
        c = rl.Canvas(buf, pagesize=A4, invariant=1)
        c.setTitle("Synthetic statement")
        at = {"page": 1, "y": 0}

        def text(x, y, s, fnt, fsize, right=False, dx=0.0):
            c.setFont(fnt, fsize)
            x = (x - stringWidth(s, fnt, fsize) if right else x) + dx
            if not apart:
                c.drawString(x, y, s)
                return
            for word in s.split(" "):
                if word:
                    c.drawString(x, y, word)
                x += stringWidth(word + " ", fnt, fsize)

        def cell(s, i, y, fnt, fsize, dx=0.0):
            right = i >= right_from  # amounts sit at the right of their column
            text(xs[i + 1] - 3 if right else xs[i] + 3, y, s, fnt, fsize, right, dx)

        def heading():
            head = [_wrap(h, widths[i] - 6, bold, head_size) for i, h in enumerate(header)]
            depth = max(map(len, head))
            for i, lines in enumerate(head):
                off = (depth - len(lines)) * lead / 2 if heading_align == "middle" else 0
                for k, s in enumerate(lines):
                    for dx in ((0.0, 0.35) if bold_twice else (0.0,)):
                        cell(s, i, at["y"] - off - k * lead, bold, head_size, dx)
            at["y"] -= depth * lead + 3
            if grid:
                c.line(xs[0], at["y"] + lead - 1, xs[-1], at["y"] + lead - 1)

        def end_page():
            c.setFont(font, 6.2)
            for k, s in enumerate(footer):
                c.drawString(left, 30 + 9 * (len(footer) - k), s)
            c.setFont(font, 6.5)
            c.drawCentredString(A4[0] / 2, 22, f"Page {at['page']} of {total}")
            c.showPage()
            at["page"] += 1

        def new_page():
            end_page()
            at["y"] = page_top(c, at["page"])
            if repeat_heading:
                heading()

        at["y"] = page_top(c, 1)
        heading()
        for n_row, row in enumerate(rows):
            if n_row == note_after:
                at["y"] -= 2 * lead
                text(xs[1] + 3, at["y"], "Balance brought forward from the previous period", font, size)
                at["y"] -= 2 * lead
            cells = [_wrap(str(v), widths[i] - 6, font, size, wrap) if v else []
                     for i, v in enumerate(row)]
            depth = max(1, max(map(len, cells)))
            if at["y"] - (lead if split_rows else depth * lead) < bottom:
                new_page()
            top = at["y"]
            if split_rows:  # line by line, carrying on over the page break
                y = top
                for k in range(depth):
                    if y < bottom:
                        new_page()
                        y = at["y"]
                    for i, lines in enumerate(cells):
                        if k < len(lines):
                            cell(lines[k], i, y, font, size)
                    y -= lead
                at["y"] = y - 2
                continue
            for i, lines in enumerate(cells):
                off = (depth - len(lines)) * lead * drop
                for k, s in enumerate(lines):
                    cell(s, i, top - off - k * lead, font, size)
            at["y"] = top - depth * lead - 2
            if grid:
                c.setLineWidth(0.3)
                c.line(xs[0], at["y"] + lead - 1, xs[-1], at["y"] + lead - 1)
                for x in xs:
                    c.line(x, at["y"] + lead - 1, x, top + lead - 1)
        at["y"] -= 14
        for s, fnt in closing:
            if at["y"] < bottom:
                end_page()
                at["y"] = page_top(c, at["page"])
            c.setFont(fnt, 7.5)
            c.drawString(left, at["y"], s)
            at["y"] -= 11
        if row_after_closing:
            at["y"] -= 11
            for i, v in enumerate(row_after_closing):
                if v:
                    cell(v, i, at["y"], font, size)
        end_page()
        c.save()
        return buf.getvalue(), at["page"] - 1

    _, pages = draw(0)  # "Page N of M" needs M: count the pages first
    return draw(pages)[0]


def hdfc_pdf(**style) -> bytes:
    """HDFC's statement PDF: the page head repeated on every page, the table
    without rules, the STATEMENT SUMMARY after it, the bank's footer."""
    ledger = _hdfc_ledger()
    if style.pop("newest_first", False):
        ledger = ledger[::-1]

    def top(c, page):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(36, 800, "HDFC BANK Ltd.")
        c.setFont("Helvetica", 7.5)
        c.drawString(250, 800, f"Page No .: {page}")
        c.drawString(420, 800, "Statement of accounts")
        c.drawString(36, 788, LABEL)
        if page > 1:
            return 770
        left = ["MR. SAMPLE CUSTOMER", "FLAT 1 SAMPLE APARTMENTS", "SAMPLE COLONY", "HYDERABAD 500000",
                "TELANGANA INDIA", "JOINT HOLDERS :", "Nomination : Registered",
                "Statement From : 01/06/2026 To : 31/08/2026"]
        right = ["Account Branch : SAMPLE BRANCH", "City : HYDERABAD 500000", "State : TELANGANA",
                 "Currency : INR", "Cust ID : XXXXXXXX", "Account No : XXXXXXXXXX2626",
                 "Account Status : Regular", "RTGS/NEFT IFSC : HDFC0XXXXXX"]
        for k, (l, r) in enumerate(zip(left, right)):
            c.drawString(36, 772 - k * 10, l)
            c.drawString(330, 772 - k * 10, r)
        return 680

    rows = [(_ddmmyy(d), text, ref, _ddmmyy(d), _indian(out) if out else "", _indian(inn) if inn else "",
             _indian(bal)) for d, text, ref, out, inn, bal in ledger]
    if style.pop("misprint", False):  # the BIL/ONL payment printed 1,463.00: its balance can't follow
        k = next(k for k, r in enumerate(rows) if r[1].startswith("BIL/ONL"))
        rows[k] = rows[k][:4] + ("1,463.00",) + rows[k][5:]
    if style.pop("second_statement", False):
        style["row_after_closing"] = ("05/09/26", "UPI-SWIGGY-SWIGGY.STORES@AXB-UTIB0000100-624812345699-UPI",
                                      "0000624812345699", "05/09/26", "500.00", "", "1,97,799.35")
    debits = [r for r in ledger if r[3]]
    credits = [r for r in ledger if r[4]]
    closing = [("STATEMENT SUMMARY  :-", "Helvetica-Bold"),
               ("Opening Balance      Dr Count     Cr Count     Debits           Credits          Closing Bal",
                "Helvetica"),
               (f"{_indian(HDFC_OPENING)}          {len(debits)}           {len(credits)}           "
                f"{_indian(sum(r[3] for r in debits))}      {_indian(sum(r[4] for r in credits))}      "
                f"{_indian(_hdfc_ledger()[-1][5])}", "Helvetica"),
               ("Generated On: 01/09/26 09:15:32   Generated By: XXXXXXXX   Requesting Branch Code: NET",
                "Helvetica"),
               ("This is a computer generated statement and does not require signature.", "Helvetica"),
               (LABEL, "Helvetica")]
    style.setdefault("footer", HDFC_FOOTER)
    return _pdf(top, ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.",
                      "Closing Balance"], [40, 178, 76, 40, 62, 62, 65], rows, closing,
                grid=False, right_from=4, **style)


def sbi_pdf(**style) -> bytes:
    """SBI's account statement PDF: the account block, then the table in a
    ruled grid, dates written 1 Jun 2026 in a column narrow enough to wrap."""
    ledger = _sbi_ledger()
    if style.pop("newest_first", False):
        ledger = ledger[::-1]

    def top(c, page):
        c.setFont("Helvetica", 7.5)
        c.drawString(36, 806, LABEL)
        if page > 1:
            return 780
        block = sbi_sheet()[1:16]
        for k, (key, _, value) in enumerate(block):
            c.drawString(36, 792 - k * 10, key)
            c.drawString(210, 792 - k * 10, f":  {value}")
        c.drawString(36, 626, "Account Statement from 1 Jun 2026 to 31 Aug 2026")
        return 606

    rows = [(f"{d.day} {d:%b %Y}", f"{d.day} {d:%b %Y}", text, ref, "99999",
             _money(out) if out else "", _money(inn) if inn else "", _money(bal))
            for d, text, ref, out, inn, bal in ledger]
    closing = [("**This is a computer generated statement and does not require a signature.", "Helvetica"),
               ("Please do not share your ATM, Debit/Credit card number, PIN and OTP with anyone.",
                "Helvetica"), (LABEL, "Helvetica")]
    style.setdefault("grid", not style.get("split_rows"))
    return _pdf(top, ["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Branch Code",
                      "Debit", "Credit", "Balance"], [44, 44, 150, 86, 34, 53, 53, 59], rows, closing,
                right_from=5, **style)


def other_bank_pdf() -> bytes:
    """A statement PDF laid out the way neither SBI nor HDFC lays one out
    (another bank's columns): it must be refused, not read."""
    ledger = _hdfc_ledger()

    def top(c, page):
        c.setFont("Helvetica", 7.5)
        c.drawString(36, 806, LABEL)
        c.drawString(36, 794, "SAMPLE OTHER BANK - DETAILED STATEMENT")
        return 770

    rows = [(str(k), _ddmmyy(d), _ddmmyy(d), ref, text, _indian(out) if out else "0.00",
             _indian(inn) if inn else "0.00", _indian(bal))
            for k, (d, text, ref, out, inn, bal) in enumerate(ledger[:12], 1)]
    return _pdf(top, ["S No.", "Value Date", "Transaction Date", "Cheque Number", "Transaction Remarks",
                      "Withdrawal Amount (INR )", "Deposit Amount (INR )", "Balance (INR )"],
                [24, 40, 46, 70, 150, 60, 60, 66], rows, [(LABEL, "Helvetica")], grid=True, right_from=5)


def scanned_pdf(hidden_text: bool = False) -> bytes:
    """A photographed statement: one picture per page, no text. With
    `hidden_text`, the invisible text a scanner's character recognition lays
    over the picture: text nobody sees, so none a reader may trust."""
    from PIL import Image, ImageDraw
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl

    img = Image.new("L", (420, 594), 250)
    draw = ImageDraw.Draw(img)
    for k in range(28):  # grey bars where a photographed statement's lines would be
        draw.rectangle((30, 90 + 17 * k, 30 + 180 + (k * 37) % 170, 97 + 17 * k), fill=90)
    buf = io.BytesIO()
    c = rl.Canvas(buf, pagesize=A4, invariant=1)
    c.setTitle("Synthetic statement")
    c.drawImage(ImageReader(img), 0, 0, *A4)
    if hidden_text:
        t = c.beginText(36, 680)
        t.setTextRenderMode(3)
        t.setFont("Helvetica", 7.3)
        t.textLine(LABEL)
        t.textLine("Date   Narration   Chq./Ref.No.   Value Dt   Withdrawal Amt.   Deposit Amt.   Closing Balance")
        for d, text, ref, out, inn, bal in _hdfc_ledger()[:10]:
            t.textLine(f"{_ddmmyy(d)}   {text[:30]}   {ref}   {_ddmmyy(d)}   {out or ''}   {inn or ''}   {bal}")
        c.drawText(t)
    c.showPage()
    c.save()
    return buf.getvalue()


def _locked_pdf(data: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    w.encrypt(SBI_PASSWORD, algorithm="AES-256")
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


# The same two statements drawn the ways other report writers draw tables
# (samples/pdf_layouts/). The reader must read every one of them exactly as
# it reads the spreadsheet, or refuse it: a layout it can't read safely
# (cells centred or bottom-aligned in their row) must stop, never be guessed.
LAYOUTS = {
    "hdfc_breaks_after_hyphens.pdf": ("hdfc", dict(wrap="hyphen")),
    "hdfc_breaks_anywhere.pdf": ("hdfc", dict(wrap="chars")),
    "hdfc_heading_on_first_page_only.pdf": ("hdfc", dict(repeat_heading=False)),
    "hdfc_rows_split_by_page_breaks.pdf": ("hdfc", dict(split_rows=True, size=8.4)),
    "hdfc_words_drawn_apart.pdf": ("hdfc", dict(apart=True)),
    "hdfc_courier.pdf": ("hdfc", dict(font="Courier")),
    "hdfc_heading_drawn_twice.pdf": ("hdfc", dict(bold_twice=True, heading_align="middle")),
    "hdfc_newest_first.pdf": ("hdfc", dict(newest_first=True)),
    "hdfc_rows_centred.pdf": ("hdfc", dict(align="middle")),
    "hdfc_rows_bottom_aligned.pdf": ("hdfc", dict(align="bottom")),
    "sbi_breaks_after_hyphens.pdf": ("sbi", dict(wrap="hyphen")),
    "sbi_breaks_anywhere.pdf": ("sbi", dict(wrap="chars")),
    "sbi_rows_split_by_page_breaks.pdf": ("sbi", dict(split_rows=True, size=9)),
    "sbi_times.pdf": ("sbi", dict(font="Times-Roman", size=8.2)),
    "sbi_words_drawn_apart.pdf": ("sbi", dict(apart=True, repeat_heading=False, size=8.2)),
    "sbi_rows_centred.pdf": ("sbi", dict(align="middle")),
    "hdfc_amount_misprinted.pdf": ("hdfc", dict(misprint=True)),
    "hdfc_note_between_rows.pdf": ("hdfc", dict(note_after=10)),
    "hdfc_row_after_summary.pdf": ("hdfc", dict(second_statement=True)),
    "other_bank.pdf": ("other", {}),
    "scanned.pdf": ("scan", {}),
    "scanned_with_hidden_text.pdf": ("scan", dict(hidden_text=True)),
}


def layout(name: str) -> bytes:
    kind, style = LAYOUTS[name]
    make = {"hdfc": hdfc_pdf, "sbi": sbi_pdf, "other": other_bank_pdf, "scan": scanned_pdf}[kind]
    return make(**dict(style))


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
        "hdfc_netbanking.pdf": hdfc_pdf(),
        "sbi_account_statement.pdf": sbi_pdf(),
        "sbi_account_statement_locked.pdf": _locked_pdf(sbi_pdf()),
    }
    for name, data in files.items():
        (OUT / name).write_bytes(data)
        print(f"wrote samples/realistic/{name} ({len(data):,} bytes)")
    LAYOUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in LAYOUTS:
        data = layout(name)
        (LAYOUT_DIR / name).write_bytes(data)
        print(f"wrote samples/pdf_layouts/{name} ({len(data):,} bytes)")


if __name__ == "__main__":
    sys.exit(main())
