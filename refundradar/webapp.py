"""The RefundRadar web app — a thin FastAPI layer over the audit engine.

Deliberately stateless: the browser holds the statement text and re-sends it
with each request, so the server stores nothing. Privacy by architecture.
"""

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from refundradar.audit import audit_csv_text, to_dict
from refundradar.complaint import generate_complaint_pack
from refundradar.model import UNSUPPORTED_CHANNELS
from refundradar.parser import parse_generic_csv_text

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
INDEX = Path(__file__).resolve().parent / "static" / "index.html"

app = FastAPI(title="RefundRadar")


class AuditRequest(BaseModel):
    csv: str
    confirmed: list[str] = []
    as_of: str | None = None


class ComplaintRequest(AuditRequest):
    name: str
    account_last4: str
    contact: str


def _audit(req: AuditRequest):
    as_of = date.fromisoformat(req.as_of) if req.as_of else None
    try:
        return audit_csv_text(req.csv, set(req.confirmed), as_of=as_of)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Could not read that file as a statement CSV. Expected "
                   "columns: Date, Narration, Ref, Debit, Credit, Balance.",
        ) from None


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
    a = _audit(req)
    flagged = {i.txn.ref for i in a.incidents}
    candidates = [
        {
            "ref": t.ref,
            "date": t.txn_date.isoformat(),
            "amount": str(t.amount),
            "narration": t.narration,
        }
        for t in parse_generic_csv_text(req.csv)
        if t.is_debit and t.ref and t.ref not in flagged
        and t.channel and t.channel not in UNSUPPORTED_CHANNELS
    ]
    return {"audit": to_dict(a), "candidates": candidates}


@app.post("/api/complaint", response_class=PlainTextResponse)
def complaint_endpoint(req: ComplaintRequest) -> str:
    a = _audit(req)
    return generate_complaint_pack(a, req.name, req.account_last4, req.contact)
