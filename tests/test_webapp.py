"""The web layer: every endpoint, the happy path and the failure path."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refundradar.webapp import app

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
AS_OF = "2026-07-23"

client = TestClient(app)


@pytest.fixture(scope="module")
def demo_csv():
    return (SAMPLES / "demo_statement.csv").read_text(encoding="utf-8-sig")


def test_index_serves_the_app():
    res = client.get("/")
    assert res.status_code == 200
    assert "RefundRadar" in res.text
    assert "Drop your bank statement" in res.text


def test_demo_endpoint(demo_csv):
    res = client.get("/api/demo")
    assert res.status_code == 200
    data = res.json()
    assert data["csv"].startswith("Date,Narration")
    assert len(data["suggested_confirmed"]) == 1


def test_audit_endpoint_without_confirmation(demo_csv):
    res = client.post("/api/audit", json={"csv": demo_csv, "as_of": AS_OF})
    assert res.status_code == 200
    a = res.json()["audit"]
    assert a["total_owed_inr"] == 1400
    assert a["on_time_count"] == 1
    assert res.json()["candidates"], "unflagged debits offered for confirmation"


def test_audit_endpoint_with_confirmation(demo_csv):
    ref = client.get("/api/demo").json()["suggested_confirmed"][0]
    res = client.post("/api/audit",
                      json={"csv": demo_csv, "confirmed": [ref], "as_of": AS_OF})
    a = res.json()["audit"]
    assert a["total_owed_inr"] == 1400 + 3700
    from decimal import Decimal
    assert Decimal(a["stuck_amount"]) == Decimal(2499)


def test_complaint_endpoint(demo_csv):
    ref = client.get("/api/demo").json()["suggested_confirmed"][0]
    res = client.post("/api/complaint", json={
        "csv": demo_csv, "confirmed": [ref], "as_of": AS_OF,
        "name": "Dhanush Jangadi", "account_last4": "2626",
        "contact": "test@example.com",
    })
    assert res.status_code == 200
    assert "Rs.5100" in res.text
    assert "RBI/2019-20/67" in res.text


def test_bad_file_gets_clear_400():
    res = client.post("/api/audit", json={"csv": "not,a,statement\n1,2,3\n"})
    assert res.status_code == 400
    assert "Unrecognized statement format" in res.json()["detail"]
