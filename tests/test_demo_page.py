"""The live demo is the app itself: the app's own page, and the app's own routes
running in the visitor's browser, with the browser forbidding the page to send
anything to any other site."""

import base64
import csv
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_demo_page as bd
from refundradar.webapp import INDEX, app

DOCS = ROOT / "docs"
SAMPLES = ROOT / "samples"
PAGE = bd.render()


def test_committed_demo_is_this_build_of_this_app():
    """docs/ is what GitHub Pages serves at the README's live-demo link."""
    stale = "docs/ is out of date: run python tools/build_demo_page.py"
    assert (DOCS / "index.html").read_text(encoding="utf-8") == PAGE, stale
    assert (DOCS / "engine.zip").read_bytes() == bd.build_engine(), stale


def test_the_demo_page_is_the_apps_own_page():
    app_page = INDEX.read_text(encoding="utf-8")
    style = re.search(r"<style>.*?</style>", app_page, re.S).group(0)
    shared = re.findall(r"<script>.*?</script>", bd.SWAP.sub("", app_page), re.S)
    assert len(shared) == 3  # the theme, the view, and reading a file and asking about it
    assert style in PAGE and all(s in PAGE for s in shared)
    for control in ('<input type="file" id="file" accept=".csv,.xls,.xlsx,.txt" hidden>',
                    'id="drop"', 'id="demo-btn"', 'id="search"', 'id="c-name"',
                    'data-theme-choice="light"'):
        assert control in PAGE, control
    assert "synthetically tested, not yet verified against a real HDFC export" in PAGE
    assert "--bg: #0a0b0d" in PAGE and "#f7f6f3" not in PAGE  # the dark app, not the retired page


def test_the_build_refuses_a_page_whose_swaps_it_does_not_know(tmp_path, monkeypatch):
    page = INDEX.read_text(encoding="utf-8").replace("<!-- demo-swap:footer -->", "", 1)
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    monkeypatch.setattr(bd, "INDEX", tmp_path / "index.html")
    with pytest.raises(SystemExit):
        bd.render()


def test_the_demo_engine_is_the_apps_code():
    z = zipfile.ZipFile(DOCS / "engine.zip")
    app_code = {f"refundradar/{p.name}" for p in (ROOT / "refundradar").glob("*.py")}
    stand_ins = {p.relative_to(bd.ENGINE_SOURCE).as_posix() for p in bd.ENGINE_SOURCE.rglob("*.py")}
    data = {"rules/rbi_tat.yaml", "samples/demo_statement.csv", "samples/ground_truth.json"}
    assert set(z.namelist()) == app_code | stand_ins | data
    for name in app_code | data:
        assert z.read(name) == (ROOT / name).read_text(encoding="utf-8").encode("utf-8"), name


def test_the_demo_page_cannot_send_a_statement_anywhere():
    policy = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', PAGE).group(1)
    csp = dict(d.strip().split(" ", 1) for d in policy.split(";"))
    assert csp["default-src"] == csp["connect-src"] == "'self'"  # fetch from its own site only
    assert csp["form-action"] == csp["base-uri"] == csp["object-src"] == "'none'"
    assert "'unsafe-eval'" not in csp["script-src"]
    lowered = PAGE.lower()
    for reach in ("<form", "xmlhttprequest", "websocket", "sendbeacon", "eventsource", "<iframe"):
        assert reach not in lowered, reach
    assert all(not re.match(r"(https?:)?//", src) for src in re.findall(r'\ssrc="([^"]+)"', PAGE))
    # its one network call fetches the engine files; every request is answered in the page
    assert PAGE.count("fetch(") == 1 and "await (await fetch(f)).arrayBuffer()" in PAGE


def test_the_vendored_runtime_is_the_pinned_one():
    bd.check_runtime()
    vendored = {p.relative_to(DOCS).as_posix() for d in ("pyodide", "vendor")
                for p in (DOCS / d).iterdir()}
    assert vendored == set(bd.RUNTIME)  # nothing unpinned rides along


def test_what_opens_locked_files_is_pyodides_own_build_fetched_only_when_needed():
    lock = json.loads((DOCS / "pyodide" / "pyodide-lock.json").read_text())["packages"]
    for name in bd.UNLOCK:  # the wheels pyodide.loadPackage fetches, as its lock names them
        wheel = f"pyodide/{lock[name]['file_name']}"
        assert bd.RUNTIME[wheel] == lock[name]["sha256"], name
    assert set(bd.UNLOCK) == {"cryptography", *lock["cryptography"]["depends"],
                              *lock["cffi"]["depends"]}
    startup = re.search(r"const ENGINE_FILES = \[(.*?)\];", PAGE).group(1)
    assert "cryptography" not in startup  # not in what every visitor downloads
    assert 'py.loadPackage("cryptography")' in PAGE and "body.password" in PAGE


def test_the_page_presents_the_product_not_a_tour():
    banner = PAGE.split('<div class="demo-bar">', 1)[1].split("</div>", 1)[0]
    assert "Live demo" not in PAGE and "never uploaded" in banner
    # the same doorway as the app: upload first, the synthetic sample only a link after it
    landing = PAGE.split('<section id="screen-drop"', 1)[1].split("</section>", 1)[0]
    assert landing.index("Upload bank statement") < landing.index('id="demo-btn" class="link"')
    assert "suggested_confirmed" not in PAGE  # nothing is answered for the visitor


# ------------------------------------------------ the engine answers as the app does

DRIVER = """
import json, sys
sys.path.insert(0, sys.argv[1])
assert not any("-packages" in p for p in sys.path), sys.path  # nothing installed is reachable
import bridge, fastapi, pydantic, yaml
assert all(m.__file__.startswith(sys.argv[1]) for m in (bridge, fastapi, pydantic, yaml))
# as the page sends them: the body as JSON text, none for a GET
print(json.dumps([bridge.call(m, p, "" if b is None else json.dumps(b))
                  for m, p, b in json.loads(sys.stdin.read())]))
"""
DELIMITED = (
    " Date     ,Narration                                                       "
    ",Value Dat,Debit Amount       ,Credit Amount      ,Chq/Ref Number   ,Closing Balance\n"
    " 03/02/26 ,UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-PAYMENT  "
    ",03/02/26 ,           450.00  ,             0.00  ,0000603412345678 ,       39550.00\n"
    " 05/02/26 ,UPI-SWIGGY-SWIGGY.ORDER@ICICI-ICIC0DC0099-603412345678-REVERSAL "
    ",05/02/26 ,             0.00  ,           450.00  ,0000603412345678 ,       40000.00\n"
).encode()


def _xlsx(data: bytes) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    for row in csv.reader(data.decode("utf-8").splitlines()):
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _locked(data: bytes) -> bytes:
    from msoffcrypto.format.ooxml import OOXMLFile
    out = io.BytesIO()
    OOXMLFile(io.BytesIO(data)).encrypt("Sample@2626", out)
    return out.getvalue()


def _requests():
    hdfc = (SAMPLES / "hdfc_statement.csv").read_bytes()
    xls = (SAMPLES / "hdfc_statement.xls").read_bytes()
    sbi = (SAMPLES / "sbi_statement.xlsx").read_bytes()
    demo = (SAMPLES / "demo_statement.csv").read_text(encoding="utf-8-sig")
    up = lambda data, name, **kw: {"file": base64.b64encode(data).decode(), "filename": name,
                                   "as_of": "2026-04-30", **kw}
    look = lambda data, name: {"file": base64.b64encode(data).decode(), "filename": name}
    claim = {"name": "A. Sample Customer", "account_last4": "2626", "contact": "sample@example.com"}
    return [
        ("GET", "/api/demo", None),
        # what the file is, before any audit
        ("POST", "/api/statement", look(sbi, "sbi_statement.xlsx")),
        ("POST", "/api/statement", look(xls, "hdfc_statement.xls")),
        ("POST", "/api/statement", look(DELIMITED, "hdfc_delimited.txt")),
        ("POST", "/api/statement", {"csv": demo}),
        ("POST", "/api/statement", look(_locked(sbi), "sbi_statement.xlsx")),  # asks for its password
        ("POST", "/api/statement", look(b"Dear diary, nothing to see.\n", "notes.txt")),
        ("POST", "/api/audit", {**up(sbi, "sbi_statement.xlsx", confirmed_rows=[5]),
                                "as_of": "2026-09-01"}),
        ("POST", "/api/complaint", {**up(sbi, "sbi_statement.xlsx", confirmed_rows=[5, 8],
                                         pairs=[[3, 6]]), "as_of": "2026-09-01", **claim}),
        ("POST", "/api/audit", {"csv": demo, "confirmed": ["444363915096"], "as_of": "2026-07-24"}),
        ("POST", "/api/audit", up(hdfc, "hdfc_statement.csv")),
        ("POST", "/api/audit", up(xls, "hdfc_statement.xls", confirmed=["607912345678"], confirmed_rows=[9])),
        ("POST", "/api/audit", up(_xlsx(hdfc), "hdfc_statement.xlsx", confirmed_rows=[2, 14])),
        ("POST", "/api/audit", up(DELIMITED, "hdfc_delimited.txt")),
        ("POST", "/api/complaint", {**up(xls, "hdfc_statement.xls", confirmed_rows=[9]), **claim}),
        # refused, as the app refuses them
        ("POST", "/api/audit", up(b"%PDF-1.7\n1 0 obj\n", "statement.pdf")),
        ("POST", "/api/audit", up(hdfc.replace(b'450.00,"87,500.00"', b'450.00 Cr,"87,500.00"'),
                                  "hdfc_statement.csv")),
        ("POST", "/api/audit", up(b"Dear diary, nothing to see.\n", "notes.txt")),
        ("POST", "/api/audit", up(hdfc, "hdfc_statement.csv", confirmed_rows=[1])),
        ("POST", "/api/audit", up(hdfc, "hdfc_statement.csv", confirmed_rows=[999])),
        ("POST", "/api/audit", up(hdfc, "hdfc_statement.csv", pairs=[[2, 999]])),
        ("POST", "/api/audit", {"filename": "nothing.csv"}),
        ("POST", "/api/audit", up(hdfc, "hdfc_statement.csv", confirmed_rows=["x"])),
        ("POST", "/api/complaint", up(hdfc, "hdfc_statement.csv")),
    ]


@pytest.fixture(scope="module")
def engine_dir(tmp_path_factory):
    """The demo's engine as the browser unpacks it: its own files, nothing else."""
    d = tmp_path_factory.mktemp("engine")
    for p in [*bd.PACKAGES, "engine.zip"]:
        zipfile.ZipFile(DOCS / p).extractall(d)
    return d


def test_the_demo_engine_answers_every_request_as_the_app_does(engine_dir):
    requests = _requests()
    # -I -S: no installed packages at all, so FastAPI, pydantic, PyYAML and the
    # spreadsheet readers can only come from what the demo ships
    run = subprocess.run([sys.executable, "-I", "-S", "-c", DRIVER, str(engine_dir)],
                         input=json.dumps(requests), capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-2000:]
    client = TestClient(app)
    for (method, path, body), (status, kind, text) in zip(requests, json.loads(run.stdout),
                                                          strict=True):
        want = client.request(method, path, json=body)
        label = f"{method} {path} {sorted(body or {})}"
        assert status == want.status_code, (label, text[:300])
        if status == 422:
            continue  # both refuse; FastAPI also lists the fields
        if kind.startswith("application/json"):
            assert json.loads(text) == want.json(), label
        else:
            assert text == want.text, label
