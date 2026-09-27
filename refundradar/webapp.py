"""The RefundRadar web app — a thin FastAPI layer over the audit engine.

Deliberately stateless: the browser holds the statement (CSV text, or an
uploaded file's bytes as base64) and re-sends it with each request, so the
server stores nothing and never writes an upload to disk. Privacy by
architecture.
"""

import base64
import binascii
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from refundradar.audit import build_audit, to_dict
from refundradar.complaint import generate_complaint_pack
from refundradar.formats import EncryptedStatement, WrongPassword, decrypt, sniff
from refundradar.model import UNSUPPORTED_CHANNELS, Transaction
from refundradar.parser import NO_BANK_TABLE, parse_generic_csv_text, parse_statement_bytes
from refundradar.reconcile import CONFIRM, has_reference, refund_like, unmatched_refunds
from refundradar.rules_engine import load_rules

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
INDEX = Path(__file__).resolve().parent / "static" / "index.html"

# How far each reader has been proven, shown beside every result (D10, D16).
VERIFICATION = {
    "SBI": "SBI export: the layout was field-tested on one real SBI statement (July 2026); "
           "the stricter row checks added since are synthetically tested.",
    "HDFC": "HDFC export: synthetically tested, not yet verified against a real HDFC export.",
    "generic": "Generic CSV (Date, Narration, Ref, Debit, Credit, Balance).",
}

# What a file is, by its bytes (formats.sniff), in words
FILE_TYPES = {"xlsx": "Excel workbook (.xlsx)", "xls": "Excel 97-2003 workbook (.xls)",
              "text": "CSV or delimited text"}

READS = ("RefundRadar reads SBI exports (.xlsx, .xls, .csv), HDFC exports (.xls, .xlsx, "
         ".csv, or the Delimited .txt), and CSV with the columns Date, Narration, Ref, "
         "Debit, Credit, Balance.")

# Plain names for channel codes, for findings that carry no ruling.
CHANNEL_NAMES = {c["code"]: c["name"] for c in load_rules()["channels"]}

NO_TABLE = "Could not find a statement table in {name}. " + READS

app = FastAPI(title="RefundRadar")


class StatementRequest(BaseModel):
    csv: str | None = None
    file: str | None = None
    filename: str | None = None
    password: str | None = None   # opens a locked file once; never stored, never sent back


class AuditRequest(BaseModel):
    csv: str | None = None        # generic CSV text (the demo, earlier clients)
    file: str | None = None       # any supported statement file's bytes, base64
    filename: str | None = None
    confirmed: list[str] = []
    confirmed_rows: list[int] = []  # payments printed without a reference, by row (D14)
    pairs: list[tuple[int, int]] = []  # (payment, refund) the user matched by hand
    as_of: str | None = None


class ComplaintRequest(AuditRequest):
    name: str
    account_last4: str
    contact: str


def _file_bytes(req) -> bytes:
    try:
        return base64.b64decode(req.file, validate=True)
    except binascii.Error:
        raise HTTPException(status_code=400,
                            detail="The file arrived damaged. Choose it again.") from None


def _transactions(req) -> list[Transaction]:
    """Every transaction on the statement, or a refusal that says why (D10, D16)."""
    if (req.csv is None) == (req.file is None):
        raise HTTPException(status_code=400,
                            detail="Send the statement either as CSV text or as a file.")
    name = req.filename or "that file"
    try:
        if req.file is None:
            return parse_generic_csv_text(req.csv)
        return parse_statement_bytes(_file_bytes(req))
    except EncryptedStatement:
        raise HTTPException(
            status_code=400,
            detail=f"{name} is password-protected by your bank. Choose it again and "
                   "enter its password to open it on this device.") from None
    except ValueError as e:
        # the parser's own words: they name the row, column and cell
        detail = str(e)
        if detail == NO_BANK_TABLE:
            detail = NO_TABLE.format(name=name)  # last reader tried
        raise HTTPException(status_code=400, detail=detail) from None
    except HTTPException:
        raise
    except Exception:
        detail = (
            "Could not read that file as a statement CSV. Expected columns: "
            "Date, Narration, Ref, Debit, Credit, Balance."
            if req.file is None else
            f"Could not read {name} as a bank statement. " + READS
        )
        raise HTTPException(status_code=400, detail=detail) from None


def _chosen_refunds(req: AuditRequest, txns: list[Transaction]) -> list[tuple]:
    """The refunds the user matched to payments by hand, checked against
    this statement: the same amount, the refund on or after the payment."""
    chosen = []
    for p, r in req.pairs:
        fits = 0 <= p < len(txns) and 0 <= r < len(txns)
        if fits:
            d, c = txns[p], txns[r]
            fits = (d.is_debit and not c.is_debit and d.amount == c.amount
                    and c.txn_date >= d.txn_date)
        if not fits:
            raise HTTPException(
                status_code=400,
                detail="A refund you matched doesn't fit this statement. "
                       "Start over and match it again.")
        chosen.append((d, c))
    if (len({p for p, _ in req.pairs}) < len(req.pairs)
            or len({r for _, r in req.pairs}) < len(req.pairs)):
        raise HTTPException(status_code=400,
                            detail="Each payment and each refund can be matched only once.")
    return chosen


def _confirmable(t: Transaction) -> bool:
    """A payment the user may say failed: a debit on a channel the 2019
    circular covers. Its failure can't show on the statement (D6)."""
    return t.is_debit and bool(t.channel) and t.channel not in UNSUPPORTED_CHANNELS


def _confirmed_rows(req: AuditRequest, txns: list[Transaction]) -> list[Transaction]:
    """The payments without a reference the user said failed, by their row
    on this statement (D14). A payment with a reference is confirmed by it."""
    if len(set(req.confirmed_rows)) < len(req.confirmed_rows):
        raise HTTPException(status_code=400, detail="Each payment can be confirmed only once.")
    chosen = []
    for n in req.confirmed_rows:
        t = txns[n] if 0 <= n < len(txns) else None
        if t is None or has_reference(t) or not _confirmable(t):
            raise HTTPException(
                status_code=400,
                detail="A payment you confirmed doesn't fit this statement. "
                       "Start over and confirm it again.")
        chosen.append(t)
    return chosen


def _audit(req: AuditRequest):
    txns = _transactions(req)
    as_of = date.fromisoformat(req.as_of) if req.as_of else None
    return txns, build_audit(txns, set(req.confirmed), as_of=as_of,
                             confirmed_refunds=_chosen_refunds(req, txns),
                             confirmed_failed_txns=_confirmed_rows(req, txns))


def _row(t: Transaction, ids: dict) -> dict:
    return {"txn_id": ids[id(t)], "date": t.txn_date.isoformat(),
            "amount": str(t.amount), "narration": t.narration}


def _action(i, confirmed: set[str]) -> str:
    """The answer the UI may ask for; without one, nothing is claimed."""
    if i.status != CONFIRM:
        return "none"
    if i.candidates:
        return "choose_refund"   # a confirmed failure with competing credits
    if i.txn.ref and i.txn.ref not in confirmed:
        return "confirm_failed"  # "Yes, it failed"
    if i.refund_txn is not None:
        return "confirm_refund"  # no reference to confirm by: confirm the pairing
    return "none"                # unable to conclusively match


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/demo")
def demo() -> dict:
    """The synthetic sample statement, for trying RefundRadar without one of
    your own. It is audited like any upload: nothing is answered for you."""
    return {"csv": (SAMPLES / "demo_statement.csv").read_text(encoding="utf-8-sig")}


@app.post("/api/statement")
def statement_endpoint(req: StatementRequest) -> dict:
    """What the file is, before any audit: whose export, how many transactions
    were read (every row, or it is refused) and over which dates. A file the
    bank locked is opened here with the password the user typed and handed
    back open, so the password is used once and kept nowhere (D17)."""
    unlocked = None
    if req.file is not None and req.csv is None:
        data = _file_bytes(req)
        if sniff(data) == "encrypted":
            if not req.password:
                return {"locked": True, "wrong_password": False, "filename": req.filename}
            try:
                data = decrypt(data, req.password)
            except WrongPassword:
                return {"locked": True, "wrong_password": True, "filename": req.filename}
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail=f"{req.filename or 'That file'} is password-protected, and "
                           "opening it failed. Save it unprotected from Excel and "
                           "choose that copy.") from None
            unlocked = base64.b64encode(data).decode()
            req = StatementRequest(file=unlocked, filename=req.filename)
    txns = _transactions(req)
    bank = txns[0].bank if txns else "generic"
    dates = sorted(t.txn_date for t in txns)
    kind = "text" if req.file is None else sniff(_file_bytes(req))
    return {
        "locked": False,
        "filename": req.filename,
        "unlocked_file": unlocked,  # the file opened, when it came locked
        "bank": bank,
        "file_type": FILE_TYPES.get(kind, kind),
        "transactions": len(txns),
        "payments": sum(t.is_debit for t in txns),
        "credits": sum(not t.is_debit for t in txns),
        "first": dates[0].isoformat() if dates else None,
        "last": dates[-1].isoformat() if dates else None,
        "verification": VERIFICATION.get(bank, ""),
    }


@app.post("/api/audit")
def audit_endpoint(req: AuditRequest) -> dict:
    txns, a = _audit(req)
    ids = {id(t): n for n, t in enumerate(txns)}
    confirmed = set(req.confirmed)
    audit = to_dict(a)
    for d, i in zip(audit["incidents"], a.incidents):
        d["channel_name"] = d["channel_name"] or CHANNEL_NAMES.get(i.txn.channel)
        d.update(txn_id=ids[id(i.txn)], action=_action(i, confirmed),
                 refund_id=ids[id(i.refund_txn)] if i.refund_txn is not None else None,
                 candidates=[_row(c, ids) for c in i.candidates])
    loose = unmatched_refunds(txns, a.incidents)
    unmatched = [{"refund": _row(c, ids), "candidates": [_row(d, ids) for d in cands]}
                 for c, cands in loose]
    found = ({id(i.refund_txn) for i in a.incidents if i.refund_txn is not None}
             | {id(c) for i in a.incidents for c in i.candidates if refund_like(c)}
             | {id(c) for c, _ in loose})
    asked = sum(d["action"] in ("confirm_failed", "confirm_refund") for d in audit["incidents"])
    flagged = {i.txn.ref for i in a.incidents}
    findings = {id(i.txn) for i in a.incidents}
    # offered to confirm: a payment by its reference, or, when the statement
    # prints none, by its row (D14)
    candidates = [
        {
            "ref": t.ref,
            "row": ids[id(t)],
            "date": t.txn_date.isoformat(),
            "amount": str(t.amount),
            "narration": t.narration,
        }
        for t in txns
        if _confirmable(t) and (t.ref not in flagged if t.ref
                                else not has_reference(t) and id(t) not in findings)
    ]
    fmt = txns[0].bank if txns else "generic"
    return {
        "audit": audit,
        "candidates": candidates,
        "statement": {"filename": req.filename, "format": fmt,
                      "transactions": len(txns), "verification": VERIFICATION.get(fmt, "")},
        "summary": {
            "transactions": len(txns),
            "refunds_found": len(found),
            "matched": sum(i.refund_txn is not None and i.status != CONFIRM for i in a.incidents),
            "needs_confirmation": asked,
            "unable_to_match": sum(i.status == CONFIRM for i in a.incidents) - asked + len(unmatched),
        },
        "unmatched": unmatched,
    }


@app.post("/api/complaint", response_class=PlainTextResponse)
def complaint_endpoint(req: ComplaintRequest) -> str:
    _, a = _audit(req)
    return generate_complaint_pack(a, req.name, req.account_last4, req.contact)
