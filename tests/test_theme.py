"""Dark and light: one page, each colour tuned for its own background, and
every piece of text readable (WCAG AA) in both."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_demo_page as bd
from refundradar.webapp import INDEX

PAGE = INDEX.read_text(encoding="utf-8")
CSS = re.search(r"<style>(.*?)</style>", PAGE, re.S).group(1)
DARK, LIGHT = ":root", ':root[data-theme="light"]'
# the brand's own teal looks the same on either background
SAME_IN_BOTH = {"--brand", "--brand-hover", "--accent-ink", "--mark-from", "--mark-to"}
COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")

# text colour, then what it sits on (bottom layer first): every pairing the page uses
PAIRS = [
    ("--ink", ["--bg"]), ("--ink", ["--surface"]), ("--ink", ["--surface-2"]),
    ("--ink", ["--surface-3"]),
    ("--ink-2", ["--bg"]), ("--ink-2", ["--surface"]), ("--ink-2", ["--surface-2"]),
    ("--ink-2", ["--surface-3"]), ("--ink-2", ["--surface", "--slate-soft"]),
    ("--muted", ["--bg"]), ("--muted", ["--side"]), ("--muted", ["--surface"]),
    ("--muted", ["--surface-2"]), ("--muted", ["--surface-2", "--violet-soft"]),
    ("--placeholder", ["--bg"]),
    ("--accent", ["--bg"]), ("--accent", ["--surface"]), ("--accent", ["--side", "--accent-soft"]),
    ("--gold", ["--surface-2", "--gold-soft"]), ("--coral", ["--surface-2", "--coral-soft"]),
    ("--green", ["--surface-2", "--green-soft"]), ("--violet", ["--surface-2", "--violet-soft"]),
    ("--slate", ["--surface-2", "--slate-soft"]), ("--slate", ["--surface", "--slate-soft"]),
    ("--gold", ["--surface", "--gold-glow"]), ("--coral", ["--surface"]), ("--green", ["--surface"]),
    ("--coral-ink", ["--bg", "--coral-soft"]), ("--coral-ink", ["--surface"]),
    ("--gold-ink", ["--surface", "--gold-soft"]),
    ("--accent-ink", ["--brand"]), ("--accent-ink", ["--brand-hover"]),
]


def tokens(css, selector):
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.S).group(1)
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


def theme(css, name):
    dark = tokens(css, DARK)
    return dark if name == "dark" else {**dark, **tokens(css, LIGHT)}


def rgba(value):
    if value.startswith("#"):
        h = value[1:]
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)
    parts = [float(p) for p in re.findall(r"[\d.]+", value)]
    return (parts[0] / 255, parts[1] / 255, parts[2] / 255, parts[3] if len(parts) > 3 else 1.0)


def flatten(layers):
    r, g, b, _ = layers[0]
    for lr, lg, lb, a in layers[1:]:
        r, g, b = lr * a + r * (1 - a), lg * a + g * (1 - a), lb * a + b * (1 - a)
    return r, g, b


def contrast(fg, bg):
    def lum(c):
        lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def colour_tokens(block):
    return {k: v for k, v in block.items() if COLOUR.fullmatch(v)}


def test_every_colour_has_its_own_light_value():
    dark, light = colour_tokens(tokens(CSS, DARK)), tokens(CSS, LIGHT)
    missing = sorted(set(dark) - SAME_IN_BOTH - set(light))
    unchanged = sorted(k for k in set(dark) - SAME_IN_BOTH if light.get(k) == dark[k])
    assert not missing and not unchanged, f"no light value: {missing}; same as dark: {unchanged}"


def test_rules_name_colours_instead_of_writing_them():
    """A colour written into a rule would stay the same in both themes."""
    for css in (CSS, bd.DEMO_CSS):
        rules = re.sub(r':root(\[data-theme="light"\])?\s*\{.*?\}', "", css, flags=re.S)
        rules = re.sub(r"url\([^)]*\)", "", rules)  # icon masks: shapes, not colours
        assert not COLOUR.findall(rules)


@pytest.mark.parametrize("name", ["dark", "light"])
def test_text_passes_wcag_aa_in_both_themes(name):
    t = theme(CSS, name)
    low = {}
    for fg, layers in PAIRS:
        ratio = contrast(flatten([rgba(t[fg])]), flatten([rgba(t[x]) for x in layers]))
        if ratio < 4.5:
            low[f"{fg} on {'+'.join(layers)}"] = round(ratio, 2)
    assert not low


@pytest.mark.parametrize("name", ["dark", "light"])
def test_the_live_demo_banner_follows_the_theme(name):
    demo = tokens(bd.DEMO_CSS, DARK) if name == "dark" else tokens(bd.DEMO_CSS, LIGHT)
    t = theme(CSS, name)
    bar = flatten([rgba(demo["--demo-bar"])])
    for fg in ("--ink-2", "--accent"):
        assert contrast(flatten([rgba(t[fg])]), bar) >= 4.5, fg


def test_theme_switch_sits_in_the_top_corner_and_starts_dark():
    main = PAGE.split('<main class="page"', 1)[1]
    assert main.index('<div class="page-top">') < main.index('<div class="wrap">')
    assert 'class="theme" role="group" aria-label="Colour theme"' in main
    assert re.findall(r'data-theme-choice="(\w+)" aria-pressed="(\w+)"', PAGE) == [
        ("dark", "true"), ("light", "false")]
    # the page ships dark; only a visitor's own earlier choice turns it light
    assert "data-theme" not in PAGE.split("<head>", 1)[0]
    head = re.search(r"<script>(.*?)</script>", PAGE.split("</head>", 1)[0], re.S).group(1)
    assert re.findall(r'dataset\.theme = "(\w+)"', head) == ["light"]


def test_the_live_demo_has_the_same_switch():
    page = bd.render(*bd.build_demo_data())
    assert 'data-theme-choice="light"' in page and ':root[data-theme="light"]' in page
