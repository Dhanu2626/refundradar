"""Detect and open the many disguises of Indian bank statement files.

Field-tested reality: SBI exports a password-protected OLE2 container with
an .xlsx extension. Other banks ship real xlsx, legacy xls, HTML tables
renamed .xls, or plain CSV. sniff() identifies what a file really is from
its bytes; load_rows() turns any spreadsheet variant into plain rows.
"""

import io
from datetime import date, datetime

ZIP_MAGIC = b"PK\x03\x04"
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class EncryptedStatement(Exception):
    """File is password-protected; ask the user for the document password."""


def sniff(data: bytes) -> str:
    """Return xlsx | xls | encrypted | html | text for a file's raw bytes."""
    if data[:4] == ZIP_MAGIC:
        return "xlsx"
    if data[:8] == OLE_MAGIC:
        import olefile
        ole = olefile.OleFileIO(io.BytesIO(data))
        names = {"/".join(n) for n in ole.listdir()}
        return "encrypted" if "EncryptionInfo" in names else "xls"
    head = data[:2048].lstrip().lower()
    if head.startswith(b"<html") or head.startswith(b"<!doctype") or b"<table" in head:
        return "html"
    return "text"


def decrypt(data: bytes, password: str) -> bytes:
    """Decrypt a password-protected Office file to its inner package bytes."""
    import msoffcrypto
    f = msoffcrypto.OfficeFile(io.BytesIO(data))
    f.load_key(password=password)
    out = io.BytesIO()
    f.decrypt(out)
    return out.getvalue()


def _cell_date(value, datemode=0):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 20000:
        import xlrd
        return xlrd.xldate_as_datetime(value, datemode).date()
    text = str(value).strip()
    for fmt in ("%d %b %Y", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%Y-%m-%d",
                "%d-%b-%Y", "%d-%b-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def load_rows(data: bytes, password: str | None = None) -> list[list]:
    """Spreadsheet bytes (any variant) -> list of row value lists."""
    kind = sniff(data)
    if kind == "encrypted":
        if not password:
            raise EncryptedStatement(
                "This statement is password-protected by your bank. The "
                "password format is shown on the bank's download page. "
                "Re-run with the password, or open the file in Excel and "
                "Save As an unprotected CSV."
            )
        data = decrypt(data, password)
        kind = sniff(data)
    if kind == "xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        ws = wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if kind == "xls":
        import xlrd
        wb = xlrd.open_workbook(file_contents=data)
        ws = wb.sheet_by_index(0)
        rows = []
        for r in range(ws.nrows):
            rows.append([ws.cell(r, c).value for c in range(ws.ncols)])
        return rows
    raise ValueError(
        f"Unsupported statement format ({kind}). Export as Excel or CSV."
    )
