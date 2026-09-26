"""The RefundRadar web app — a thin FastAPI layer over the audit engine.

Deliberately stateless: the browser holds the statement (CSV text, or an
uploaded file's bytes as base64) and re-sends it with each request, so the
server stores nothing and never writes an upload to disk. Privacy by
architecture.
"""

import base64
import binascii
import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from refundradar.audit import build_audit, to_dict
from refundradar.complaint import generate_complaint_pack
from refundradar.formats import EncryptedStatement
from refundradar.model import UNSUPPORTED_CHANNELS, Transaction
from refundradar.parser import parse_generic_csv_text, parse_statement_bytes
from refundradar.reconcile import CONFIRM, refund_like, unmatched_refunds
from refundradar.rules_engine import load_rules

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
INDEX = Path(__file__).resolve().parent / "static" / "index.html"

# How far each reader has been proven, shown beside every result (D10).
VERIFICATION = {
    "HDFC": "HDFC export: synthetically tested, not yet verified against a real HDFC export.",
    "generic": "Generic CSV (Date, Narration, Ref, Debit, Credit, Balance).",
}

# Plain names for channel codes, for findings that carry no ruling.
CHANNEL_NAMES = {c["code"]: c["name"] for c in load_rules()["channels"]}

NO_TABLE = ("Could not find a statement table in {name}. The web app reads generic CSV "
            "(Date, Narration, Ref, Debit, Credit, Balance) and HDFC exports "
            "(.csv, .xls, .xlsx, or the Delimited .txt).")

app = FastAPI(title="RefundRadar")


class AuditRequest(BaseModel):
    csv: str | None = None        # generic CSV text (the demo, earlier clients)
    file: str | None = None       # any supported statement file's bytes, base64
    filename: str | None = None
    confirmed: list[str] = []
    pairs: list[tuple[int, int]] = []  # (payment, refund) the user matched by hand
    as_of: str | None = None


class ComplaintRequest(AuditRequest):
    name: str
    account_last4: str
    contact: str


def _transactions(req: AuditRequest) -> list[Transaction]:
    if (req.csv is None) == (req.file is None):
        raise HTTPException(status_code=400,
                            detail="Send the statement either as CSV text or as a file.")
    try:
        if req.file is None:
            return parse_generic_csv_text(req.csv)
        txns = parse_statement_bytes(base64.b64decode(req.file, validate=True))
    except binascii.Error:
        raise HTTPException(status_code=400,
                            detail="The file arrived damaged. Choose it again.") from None
    except (ValueError, EncryptedStatement) as e:
        # the parser's own words: they name the row, column and cell
        detail = str(e)
        if detail.startswith("Could not find SBI's transaction table header"):
            detail = NO_TABLE.format(name=req.filename or "that file")  # last reader tried
        raise HTTPException(status_code=400, detail=detail) from None
    except Exception:
        detail = (
            "Could not read that file as a statement CSV. Expected columns: "
            "Date, Narration, Ref, Debit, Credit, Balance."
            if req.file is None else
            f"Could not read {req.filename or 'that file'} as a bank statement. "
            "The web app reads generic CSV and HDFC exports (.csv, .xls, .xlsx, "
            "or the Delimited .txt)."
        )
        raise HTTPException(status_code=400, detail=detail) from None
    if txns and txns[0].bank == "SBI":
        # The SBI reader passes over rows it can't read; here that would be a
        # result for part of a statement.
        raise HTTPException(
            status_code=400,
            detail="This is an SBI export. The web app doesn't read SBI files yet, "
                   "because the SBI reader passes over rows it can't read and the "
                   "result could be incomplete. Audit it from the command line: "
                   "python -m refundradar audit <file>")
    return txns


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


def _audit(req: AuditRequest):
    txns = _transactions(req)
    as_of = date.fromisoformat(req.as_of) if req.as_of else None
    return txns, build_audit(txns, set(req.confirmed), as_of=as_of,
                             confirmed_refunds=_chosen_refunds(req, txns))


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
    truth = json.loads((SAMPLES / "ground_truth.json").read_text())
    suggested = [
        i["ref"] for i in truth["incidents"]
        if i["is_incident"] and i["refund_date"] is None
    ]
    return {
        "csv": (SAMPLES / "demo_statement.csv").read_text(encoding="utf-8-sig"),
        "suggested_confirmed": suggested,
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
    candidates = [
        {
            "ref": t.ref,
            "date": t.txn_date.isoformat(),
            "amount": str(t.amount),
            "narration": t.narration,
        }
        for t in txns
        if t.is_debit and t.ref and t.ref not in flagged
        and t.channel and t.channel not in UNSUPPORTED_CHANNELS
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
