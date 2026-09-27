"""The live demo's way into RefundRadar: the app's own routes
(refundradar/webapp.py), answered inside the visitor's browser instead of by a
server. docs/index.html sends each request here instead of over the network,
so a statement chosen on the demo page is read in that page and goes nowhere.

Runs under Pyodide with the stand-ins for FastAPI and pydantic that sit beside
this file (tools/demo_engine/); tests/test_demo_page.py checks that it answers
every request exactly as the real app does.
"""

import json

from fastapi import HTTPException
from pydantic import ValidationError

from refundradar import webapp

ROUTES = {
    ("GET", "/api/demo"): lambda body: webapp.demo(),
    ("POST", "/api/audit"): lambda body: webapp.audit_endpoint(webapp.AuditRequest(**body)),
    ("POST", "/api/complaint"): lambda body: webapp.complaint_endpoint(
        webapp.ComplaintRequest(**body)),
}


def call(method: str, path: str, body: str) -> list:
    """[status, content type, body text], as the app's server would answer."""
    route = ROUTES.get((method, path))
    if route is None:
        return [404, "application/json", json.dumps({"detail": "Not Found"})]
    try:
        data = json.loads(body) if body else None
        if method == "POST" and not isinstance(data, dict):
            raise ValidationError("the request body must be an object")
        result = route(data)
    except HTTPException as e:
        return [e.status_code, "application/json", json.dumps({"detail": e.detail})]
    except (ValidationError, json.JSONDecodeError) as e:
        return [422, "application/json", json.dumps({"detail": str(e)})]
    if isinstance(result, str):
        return [200, "text/plain; charset=utf-8", result]
    return [200, "application/json", json.dumps(result)]
