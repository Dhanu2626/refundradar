"""Build the public live demo (docs/) for GitHub Pages: the RefundRadar app
itself, running in the visitor's browser.

docs/index.html is the app's own page (refundradar/static/index.html) with the
blocks it marks demo-swap replaced: its title, its footer line, and send(),
which there hands each request to the app's own routes (refundradar/webapp.py)
running under Pyodide instead of on a server. docs/engine.zip carries the app's
Python code and data, plus the stand-ins in tools/demo_engine/ that let
webapp.py import without FastAPI or pydantic. Pyodide and the pure-Python
packages the parser reads spreadsheets with are vendored under docs/, pinned by
SHA-256 below, so the page loads nothing from any other site; its
Content-Security-Policy lets it connect only to its own. A statement chosen on
the demo is read in the page and sent nowhere.

Rebuild after any change to the app page or the Python package:
    python tools/build_demo_page.py
Download the pinned runtime again (from npm and PyPI, checking every digest):
    python tools/build_demo_page.py --fetch-runtime
tests/test_demo_page.py fails while docs/ is out of date.
"""

import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from refundradar.webapp import INDEX

DOCS = ROOT / "docs"
ENGINE_SOURCE = ROOT / "tools" / "demo_engine"
REPO_URL = "https://github.com/Dhanu2626/refundradar"

PYODIDE = "314.0.7"  # Python 3.14, the line CI tests on
PYODIDE_TARBALL = ("https://registry.npmjs.org/pyodide/-/pyodide-314.0.7.tgz",
                   "d18bd7c4485f11da4b7dbfd790cd8114078c44eab488c517d9bcf31fda4eb6dc"
                   "8c716930abe1db139bb2b860fcd8b37bcb6abe48dbe2ffa579244b0e943d91d4")
# the pure-Python packages the parser opens spreadsheets with (formats.py) and
# PyYAML for the rulebook, unpacked beside the app's code in this order
PACKAGES = {
    "vendor/xlrd-2.0.2-py2.py3-none-any.whl": "xlrd",
    "vendor/openpyxl-3.1.5-py2.py3-none-any.whl": "openpyxl",
    "vendor/et_xmlfile-2.0.0-py3-none-any.whl": "et-xmlfile",
    "vendor/olefile-0.47-py2.py3-none-any.whl": "olefile",
    "vendor/pyyaml-6.0.3-pure.zip": "pyyaml",  # its pure-Python half, from the source release
}
# every vendored file, by SHA-256
RUNTIME = {
    "pyodide/pyodide.js":
        "3141b814715a72e59b51b1b18b9ceae5bf19f7c852417e431bb0a34feadf825c",
    "pyodide/pyodide.asm.mjs":
        "f7cdc8ece80678ceb712f8e65ebe6d3a83203a180c399865f49612a051693635",
    "pyodide/pyodide.asm.wasm":
        "cc36e3cab04fdfc9a63ff13eb52eae2b911bf46c025cc7b281f394bd3de1d5e6",
    "pyodide/python_stdlib.zip":
        "fa1957e5777068fc4f7437f96d860ae2fbe9c19732ba06c84e004ec16dd7dd7a",
    "pyodide/pyodide-lock.json":
        "5dc2fc119108bc148c7457dc86e7675b5c87e1cafd420b9c34c1eaef7b36c010",
    "pyodide/LICENSE":
        "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5",
    "vendor/xlrd-2.0.2-py2.py3-none-any.whl":
        "ea762c3d29f4cca48d82df517b6d89fbce4db3107f9d78713e48cd321d5c9aa9",
    "vendor/openpyxl-3.1.5-py2.py3-none-any.whl":
        "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2",
    "vendor/et_xmlfile-2.0.0-py3-none-any.whl":
        "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa",
    "vendor/olefile-0.47-py2.py3-none-any.whl":
        "543c7da2a7adadf21214938bb79c83ea12b473a4b6ee4ad4bf854e7715e13d1f",
    "vendor/pyyaml-6.0.3-pure.zip":
        "5f5537e1ebd467c6ddb961466196798021ef56a94df7eb6c09e45edba68cb39d",
}

SWAP = re.compile(r"<!-- demo-swap:(\w+) -->.*?<!-- /demo-swap:\1 -->", re.S)
# The page may fetch only from its own site (the engine files) and may never
# submit a form; the browser enforces both, whatever a script tries.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'")

TITLE = f"""<title>RefundRadar — the payments auditor your bank hopes you never run</title>
<meta name="description" content="The RefundRadar app, running in your browser: audit a bank statement against RBI's failed-payment rules. Nothing is uploaded.">
<meta http-equiv="Content-Security-Policy" content="{CSP}">"""

FOOTER = ("<span>RefundRadar &mdash; applies RBI/2019-20/67 as code. This live demo runs "
          "entirely in your browser.</span>")

TRANSPORT = """<script src="pyodide/pyodide.js"></script>
<script>
// The live demo answers every request in this browser: RefundRadar's own routes
// (refundradar/webapp.py) run under Pyodide, loaded from this site, so a
// statement chosen here is read in this page and sent nowhere.
const ENGINE_FILES = [@FILES@];
let engineReady = false;
const engine = (async () => {
  const py = await loadPyodide({ indexURL: "pyodide/" });
  for (const f of ENGINE_FILES)
    py.unpackArchive(await (await fetch(f)).arrayBuffer(), "zip", { extractDir: "/engine" });
  py.runPython("import sys; sys.path.insert(0, '/engine')");
  return py.pyimport("bridge");
})();
engine.then(() => { engineReady = true; engineState("ready", "engine ready"); },
            () => engineState("failed", "the engine couldn't start in this browser"));

function engineState(state, words) {
  const el = $("engine-state");
  el.dataset.state = state;
  el.textContent = words;
}

async function send(path, body) {
  if (!engineReady) {
    setStatus("Starting the audit engine in your browser…");
    document.body.classList.add("busy");
  }
  let bridge;
  try {
    bridge = await engine;
  } catch (_) {
    document.body.classList.remove("busy");
    throw new Error("The audit engine couldn't start in this browser. " +
                    "Run RefundRadar on your computer instead: it works the same.");
  }
  await new Promise((r) => setTimeout(r, 16));  // let "Auditing…" show before the engine works
  const out = bridge.call(body === undefined ? "GET" : "POST", path,
                          body === undefined ? "" : JSON.stringify(body));
  const [status, type, text] = out.toJs();
  out.destroy();
  return new Response(text, { status, headers: { "Content-Type": type } });
}
</script>"""

BANNER = f"""<div class="demo-bar"><span class="pill">Live demo</span><span>RefundRadar runs in
  this browser: your file is read here and never uploaded &middot;
  <span id="engine-state" data-state="loading">starting the engine…</span> &middot;
  <a href="{REPO_URL}">Get it on GitHub</a></span></div>
"""

DEMO_CSS = """
  /* the live demo's few rules of its own; everything else is the app's */
  :root { --demo-bar: #0d1b1b; }
  :root[data-theme="light"] { --demo-bar: #e2f5f1; }
  .demo-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: center;
              gap: 4px 10px; min-height: 40px; padding: 8px 16px; border-bottom: 1px solid var(--line);
              background: var(--demo-bar); color: var(--ink-2); font-size: 13px; text-align: center; }
  .demo-bar .pill { padding: 2px 9px; border-radius: 999px; background: var(--brand);
                    color: var(--accent-ink); font-size: 11.5px; font-weight: 800;
                    letter-spacing: .06em; text-transform: uppercase; }
  .demo-bar a { color: var(--accent); font-weight: 600; text-underline-offset: 3px; }
  #engine-state[data-state="ready"] { color: var(--accent); font-weight: 600; }
  #engine-state[data-state="failed"] { color: var(--coral-ink); font-weight: 600; }
  .shell { min-height: calc(100vh - 40px); }
  @media (min-width: 1024px) { .side { height: calc(100vh - 40px); } }
"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip(files: dict[str, bytes]) -> bytes:
    """A zip that is the same bytes on any machine: sorted, stored, dated 1980."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])
    return buf.getvalue()


def _text(path: Path) -> bytes:
    # line endings as git stores them, whatever the checkout turned them into
    return path.read_text(encoding="utf-8").encode("utf-8")


def engine_files() -> dict[str, bytes]:
    """What the demo runs: the app's package and data, the bridge, the stand-ins."""
    files = {f"refundradar/{p.name}": _text(p) for p in (ROOT / "refundradar").glob("*.py")}
    files["rules/rbi_tat.yaml"] = _text(ROOT / "rules" / "rbi_tat.yaml")
    for name in ("demo_statement.csv", "ground_truth.json"):
        files[f"samples/{name}"] = _text(ROOT / "samples" / name)
    for p in ENGINE_SOURCE.rglob("*.py"):
        files[p.relative_to(ENGINE_SOURCE).as_posix()] = _text(p)
    return files


def build_engine() -> bytes:
    return _zip(engine_files())


def render() -> str:
    """The app's page with its demo-swap blocks replaced: the live demo."""
    page = INDEX.read_text(encoding="utf-8")
    files = ", ".join(f'"{p}"' for p in [*PACKAGES, "engine.zip"])
    parts = {"title": TITLE, "footer": FOOTER, "transport": TRANSPORT.replace("@FILES@", files)}
    marked = SWAP.findall(page)
    if sorted(marked) != sorted(parts):
        raise SystemExit(f"{INDEX.name} marks the demo-swap blocks {sorted(marked)}; "
                         f"this build replaces {sorted(parts)}. Make them agree.")
    page = SWAP.sub(lambda m: parts[m.group(1)], page)
    for anchor, added in (("</head>", f"<style>{DEMO_CSS}</style>\n</head>"),
                          ('<div class="shell">', BANNER + '<div class="shell">')):
        if page.count(anchor) != 1:
            raise SystemExit(f"{INDEX.name} no longer has exactly one {anchor!r}.")
        page = page.replace(anchor, added)
    return page


def check_runtime() -> None:
    """Every vendored file present, byte for byte the pinned one."""
    wrong = [p for p, digest in RUNTIME.items()
             if not (DOCS / p).is_file() or _sha256((DOCS / p).read_bytes()) != digest]
    if wrong:
        raise SystemExit(f"Vendored runtime missing or changed: {wrong}. "
                         "Run python tools/build_demo_page.py --fetch-runtime")


def fetch_runtime() -> None:
    """Download the pinned runtime into docs/, checking every digest on the way."""
    import json
    import tarfile
    from urllib.request import urlopen

    def get(url, sha256=None):
        data = urlopen(url, timeout=120).read()
        if sha256 and _sha256(data) != sha256:
            raise SystemExit(f"{url} does not match its published digest")
        return data

    tarball = urlopen(PYODIDE_TARBALL[0], timeout=300).read()
    if hashlib.sha512(tarball).hexdigest() != PYODIDE_TARBALL[1]:
        raise SystemExit("The Pyodide tarball does not match its npm integrity digest")
    (DOCS / "pyodide").mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tarball)) as t:
        for p in RUNTIME:
            if p.startswith("pyodide/") and p != "pyodide/LICENSE":
                (DOCS / p).write_bytes(t.extractfile("package/" + p.split("/", 1)[1]).read())
    (DOCS / "pyodide/LICENSE").write_bytes(
        get("https://raw.githubusercontent.com/pyodide/pyodide/main/LICENSE"))
    (DOCS / "vendor").mkdir(exist_ok=True)
    for p, project in PACKAGES.items():
        version = re.search(r"-(\d[\d.]*)-", p).group(1)
        meta = json.load(urlopen(f"https://pypi.org/pypi/{project}/{version}/json", timeout=60))
        if project != "pyyaml":
            [u] = [u for u in meta["urls"] if u["filename"] == p.split("/")[1]]
            (DOCS / p).write_bytes(get(u["url"], u["digests"]["sha256"]))
            continue
        [u] = [u for u in meta["urls"] if u["packagetype"] == "sdist"]
        with tarfile.open(fileobj=io.BytesIO(get(u["url"], u["digests"]["sha256"]))) as t:
            top = f"pyyaml-{version}/"
            files = {m.name[len(top) + 4:]: t.extractfile(m).read() for m in t.getmembers()
                     if m.name.startswith(top + "lib/yaml/") and m.name.endswith(".py")}
            files["yaml/LICENSE"] = t.extractfile(top + "LICENSE").read()
        (DOCS / p).write_bytes(_zip(files))
    check_runtime()


def main(argv=None) -> None:
    if "--fetch-runtime" in (sys.argv[1:] if argv is None else argv):
        fetch_runtime()
    check_runtime()
    (DOCS / "index.html").write_text(render(), encoding="utf-8", newline="\n")
    (DOCS / "engine.zip").write_bytes(build_engine())
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Wrote {DOCS / 'index.html'} and {DOCS / 'engine.zip'}: the app, running in the "
          f"browser on Pyodide {PYODIDE}")


if __name__ == "__main__":
    main()
