"""The public demo page must build, show the real number, and carry no upload."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_demo_page as bd


def test_demo_data_matches_engine():
    audit, pack = bd.build_demo_data()
    assert audit["total_owed_inr"] == 800 + 600 + 3800
    assert "RBI/2019-20/67" in pack
    assert "not legal advice" in pack


def test_rendered_page_is_safe_and_complete():
    audit, pack = bd.build_demo_data()
    page = bd.render(audit, pack)
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
