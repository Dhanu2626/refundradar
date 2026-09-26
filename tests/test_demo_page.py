"""The public demo page must be the app's own page, show the real number, and
carry no upload."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_demo_page as bd
from refundradar.webapp import (INDEX, AuditRequest, ComplaintRequest, audit_endpoint,
                                complaint_endpoint, demo)


def test_demo_data_matches_engine():
    data, pack = bd.build_demo_data()
    assert data["audit"]["total_owed_inr"] == 800 + 600 + 3800
    assert "RBI/2019-20/67" in pack
    assert "not legal advice" in pack


def test_rendered_page_is_safe_and_complete():
    data, pack = bd.build_demo_data()
    page = bd.render(data, pack)
    assert "<!doctype html>" in page.lower()
    # structurally no way to upload: no file input, no form, no fetch/upload JS
    lowered = page.lower()
    assert "<input" not in lowered
    assert "type=\"file\"" not in lowered
    assert "<form" not in lowered
    assert "fetch(" not in lowered
    # shows the real headline number and the friendly channel names
    assert "₹5,200" in page
    assert "UPI person-to-merchant" in page
    assert "upi_p2m" not in page  # raw codes must be humanized


def test_demo_page_is_the_apps_own_page():
    """The live demo can't drift from the app: it carries the app's whole
    stylesheet and findings renderer, verbatim."""
    app = INDEX.read_text(encoding="utf-8")
    page = bd.render(*bd.build_demo_data())
    style = re.search(r"<style>.*?</style>", app, re.S).group(0)
    view = re.search(r"<script>.*?</script>", app, re.S).group(0)
    assert "function render(data)" in view and "function incidentRow(i)" in view
    assert style in page and view in page
    # the dark dashboard, not the retired light page
    assert "--bg: #0a0b0d" in page and "#f7f6f3" not in page


def test_committed_demo_page_is_current():
    """docs/ is what GitHub Pages serves at the README's live-demo link."""
    committed = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert committed == bd.render(*bd.build_demo_data()), \
        "docs/index.html is out of date: run python tools/build_demo_page.py"


def test_demo_shows_what_the_app_answers_for_its_demo_statement():
    d = demo()
    req = {"csv": d["csv"], "confirmed": d["suggested_confirmed"], "as_of": bd.AS_OF.isoformat()}
    app = audit_endpoint(AuditRequest(**req))
    for i in app["audit"]["incidents"]:
        del i["channel"]  # the page names each channel; it doesn't carry the codes
    data, pack = bd.build_demo_data()
    assert data == {**app, "candidates": []}  # no search box, so no list to search
    assert pack == complaint_endpoint(ComplaintRequest(**req, **bd.SAMPLE))


def test_demo_page_loads_nothing_and_reads_no_file():
    lowered = bd.render(*bd.build_demo_data()).lower()
    for reach in ("<script src", "<link rel=\"stylesheet\"", "@import", "url(http", "src=\"http",
                  "xmlhttprequest", "websocket", "sendbeacon", "filereader", "datatransfer.files"):
        assert reach not in lowered, reach


@pytest.mark.parametrize("change", [
    # a file input outside the blocks the demo replaces
    ('<div class="features">', '<input type="file" id="file"><div class="features">'),
    # a block the build no longer finds, so its inputs would stay
    ("<!-- demo-swap:fields -->", ""),
])
def test_build_refuses_a_page_that_could_take_a_file(tmp_path, monkeypatch, change):
    page = INDEX.read_text(encoding="utf-8")
    assert page.count(change[0]) == 1
    (tmp_path / "index.html").write_text(page.replace(*change), encoding="utf-8")
    monkeypatch.setattr(bd, "INDEX", tmp_path / "index.html")
    with pytest.raises(SystemExit):
        bd.render(*bd.build_demo_data())
