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
the demo is read in the page and sent nowhere. Pyodide's own build of
cryptography, which opens a password-protected Excel file (SBI's download), is
vendored too and fetched only when a password is typed; the PDF reader
(pdfminer.six, with cryptography and Pyodide's charset-normalizer) only when a
PDF is chosen.

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
    "vendor/msoffcrypto_tool-6.0.0-py3-none-any.whl": "msoffcrypto-tool",  # opens locked files
}
# Pyodide's builds of what msoffcrypto-tool decrypts with, loaded with
# pyodide.loadPackage("cryptography") the first time a password is typed.
# They come from the Pyodide release and must match pyodide-lock.json, which
# is itself pinned below.
PYODIDE_RELEASE = (f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE}/"
                   f"pyodide-{PYODIDE}.tar.bz2")
UNLOCK = ("cryptography", "cffi", "pycparser", "six")
# Reading a PDF (pdftable.py) takes pdfminer.six, which imports cryptography
# and charset-normalizer: loaded the first time a PDF is chosen, so nobody
# else downloads them. pdfminer.six is its PyPI wheel without pdfminer/cmap/
# (8 MB of Chinese, Japanese and Korean font tables no SBI or HDFC statement
# uses); charset-normalizer is Pyodide's build, per its lock.
PDF_READER = ("vendor/pdfminer_six-20260107-nocmap.zip", "pdfminer.six", "20260107")
READ_PDF = ("charset-normalizer",)
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
    "vendor/msoffcrypto_tool-6.0.0-py3-none-any.whl":
        "46c394ed5d9641e802fc79bf3fb0666a53748b23fa8c4aa634ae9d30d46fe397",
    "pyodide/cryptography-47.0.0-cp314-abi3-pyemscripten_2026_0_wasm32.whl":
        "0b41491ced2cf85046559cac2502e875492cbef6d332addafa680e41be27f0ad",
    "pyodide/cffi-2.0.0-cp314-cp314-pyemscripten_2026_0_wasm32.whl":
        "9ae1a61096321cef7248e02293f42d000fa87b73a3e795705a2444290590459d",
    "pyodide/pycparser-3.0-py3-none-any.whl":
        "0b4cbc12c42e25df55343342fb0da45b189181e4f360602f9721db2016fc3a4b",
    "pyodide/six-1.17.0-py2.py3-none-any.whl":
        "228c50f73aa7addf2c2ccf2979c256802a59ab69cad8152b31b9443cc8140f42",
    "pyodide/charset_normalizer-3.4.7-py3-none-any.whl":
        "9e437ef92fa51f06eedeb1ef092c0a887bd24fe0d40b1e900191117ce1653121",
    "vendor/pdfminer_six-20260107-nocmap.zip":
        "5587a23f969a41552e57514f2b5e89c2f31e1b9916cc5621255cde71151abae1",
}

SWAP = re.compile(r"<!-- demo-swap:(\w+) -->.*?<!-- /demo-swap:\1 -->", re.S)
# The page may fetch only from its own site (the engine files) and may never
# submit a form; the browser enforces both, whatever a script tries.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'")

TITLE = f"""<title>RefundRadar — the payments auditor your bank hopes you never run</title>
<meta name="description" content="RefundRadar in your browser: upload an SBI or HDFC statement to find failed payments, late refunds and the compensation your bank owes. Nothing is uploaded.">
<meta http-equiv="Content-Security-Policy" content="{CSP}">"""

FOOTER = ("<span>RefundRadar &mdash; applies RBI/2019-20/67 as code. Runs entirely in "
          "your browser.</span>")

TRANSPORT = """<script src="pyodide/pyodide.js"></script>
<script>
// Every request is answered in this browser: RefundRadar's own routes
// (refundradar/webapp.py) run under Pyodide, loaded from this site, so a
// statement chosen here is read in this page and sent nowhere.
const ENGINE_FILES = [@FILES@];
const PDF_READER = "@PDF@";
let engineReady = false;

// The first visit downloads the Python runtime (the browser keeps it after):
// count it as it arrives, so a slow connection shows progress, not a stall.
// Responses pass through unchanged; only their bytes are counted.
const RUNTIME_BYTES = @BYTES@;
let arrived = 0;
const plainFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await plainFetch(...args);
  if (engineReady || !res.body || typeof TransformStream !== "function") return res;
  const counted = res.body.pipeThrough(new TransformStream({
    transform(chunk, out) { arrived += chunk.byteLength; showArrival(); out.enqueue(chunk); },
  }));
  return new Response(counted, { status: res.status, statusText: res.statusText, headers: res.headers });
};
function showArrival() {
  if (engineReady) return;
  const words = `starting… ${Math.min(99, Math.floor(100 * arrived / RUNTIME_BYTES))}% of ` +
                `${(RUNTIME_BYTES / 1e6).toFixed(1)} MB (first visit only)`;
  engineState("loading", words);
  if (document.body.classList.contains("busy")) setStatus(`Starting RefundRadar in your browser: ${words}`);
}

const runtime = loadPyodide({ indexURL: "pyodide/" });
const unpack = async (py, f) =>
  py.unpackArchive(await (await fetch(f)).arrayBuffer(), "zip", { extractDir: "/engine" });
const engine = (async () => {
  const py = await runtime;
  for (const f of ENGINE_FILES) await unpack(py, f);
  py.runPython("import sys; sys.path.insert(0, '/engine')");
  return py.pyimport("bridge");
})();
engine.then(() => { engineReady = true; engineState("ready", "ready"); },
            () => engineState("failed", "couldn't start in this browser"));

// Opening a password-protected file takes Pyodide's build of cryptography,
// from this site, checked against pyodide-lock.json: fetched the first time a
// password is typed, so nobody else downloads it. Reading a PDF takes it too,
// with Pyodide's charset-normalizer and the vendored pdfminer.six: fetched the
// first time a PDF is chosen.
let unlocker = null;
let pdfReader = null;
const canUnlock = () => unlocker ??= runtime.then((py) => py.loadPackage("cryptography"));
const canReadPdf = () => pdfReader ??= runtime.then(async (py) => {
  await py.loadPackage(["cryptography", "charset-normalizer"]);
  await unpack(py, PDF_READER);
  py.runPython("import importlib; importlib.invalidate_caches()");  // /engine gained files
});
function isPdf(file) {  // a PDF's header is in its first kilobyte
  try { return typeof file === "string" && atob(file.slice(0, 1368)).includes("%PDF-"); }
  catch (_) { return false; }
}

function engineState(state, words) {
  const el = $("engine-state");
  el.dataset.state = state;
  el.textContent = words;
}

async function send(path, body) {
  if (!engineReady) {
    setStatus("Starting RefundRadar in your browser…");
    document.body.classList.add("busy");
  }
  let bridge;
  try {
    bridge = await engine;
  } catch (_) {
    document.body.classList.remove("busy");
    throw new Error("RefundRadar couldn't start in this browser. Update it, or open this page in " +
                    "a current Chrome, Edge, Firefox or Safari (iPhone: iOS 16.4 or later).");
  }
  const pdf = body !== undefined && isPdf(body.file);
  if (pdf && pdfReader === null)
    setStatus("Loading the PDF reader: @PDF_MB@ MB, the first time a PDF is read…");
  if (pdf || (body !== undefined && body.password)) {
    try {
      await (pdf ? canReadPdf() : canUnlock());
    } catch (_) {
      unlocker = pdfReader = null;
      throw new Error(pdf ? "The part that reads PDFs couldn't load. Try again, or download " +
                            "the statement as Excel or CSV and choose that."
                          : "The part that opens password-protected files couldn't load. Try " +
                            "again, or save the file unprotected from Excel and choose that copy.");
    }
  }
  await new Promise((r) => setTimeout(r, 16));  // let "Auditing…" show before the engine works
  const out = bridge.call(body === undefined ? "GET" : "POST", path,
                          body === undefined ? "" : JSON.stringify(body));
  const [status, type, text] = out.toJs();
  out.destroy();
  return new Response(text, { status, headers: { "Content-Type": type } });
}
</script>"""

BANNER = f"""<div class="demo-bar"><span><svg class="ic" aria-hidden="true"><use href="#i-lock"/></svg> RefundRadar
  runs entirely in this browser: your statement is read on this device and never uploaded
  &middot; <span id="engine-state" data-state="loading">starting…</span> &middot;
  <a href="{REPO_URL}">Source on GitHub</a></span></div>
"""

DEMO_CSS = """
  /* the live demo's few rules of its own; everything else is the app's */
  :root { --demo-bar: #0d1b1b; }
  :root[data-theme="light"] { --demo-bar: #e2f5f1; }
  .demo-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: center;
              gap: 4px 10px; min-height: 40px; padding: 8px 16px; border-bottom: 1px solid var(--line);
              background: var(--demo-bar); color: var(--ink-2); font-size: 13px; text-align: center; }
  .demo-bar svg { width: 15px; height: 15px; vertical-align: -2px; color: var(--accent); }
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


def runtime_bytes() -> int:
    """What the page fetches before it can read a statement: Pyodide's wasm,
    standard library and lock file, the packages and the engine."""
    fetched = ["pyodide/pyodide.asm.wasm", "pyodide/python_stdlib.zip", "pyodide/pyodide-lock.json",
               *PACKAGES]
    return sum((DOCS / f).stat().st_size for f in fetched) + len(build_engine())


def pyodide_wheels(names) -> list[str]:
    """The vendored wheels pyodide.loadPackage fetches for `names`, per its lock."""
    import json
    lock = json.loads((DOCS / "pyodide" / "pyodide-lock.json").read_bytes())["packages"]
    return [f"pyodide/{lock[n]['file_name']}" for n in names]


def pdf_bytes() -> int:
    """What the first PDF adds: the PDF reader and what it imports."""
    return sum((DOCS / f).stat().st_size
               for f in [PDF_READER[0], *pyodide_wheels((*UNLOCK, *READ_PDF))])


def render() -> str:
    """The app's page with its demo-swap blocks replaced: the live demo."""
    page = INDEX.read_text(encoding="utf-8")
    files = ", ".join(f'"{p}"' for p in [*PACKAGES, "engine.zip"])
    transport = (TRANSPORT.replace("@FILES@", files).replace("@BYTES@", str(runtime_bytes()))
                 .replace("@PDF@", PDF_READER[0]).replace("@PDF_MB@", f"{pdf_bytes() / 1e6:.1f}"))
    parts = {"title": TITLE, "footer": FOOTER, "transport": transport}
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


def _pinned(p: str) -> bool:
    return (DOCS / p).is_file() and _sha256((DOCS / p).read_bytes()) == RUNTIME[p]


def pdf_reader_zip(wheel: bytes) -> bytes:
    """pdfminer.six's wheel as the demo ships it: every file but pdfminer/cmap/
    (and the RECORD that lists them), in a zip that is the same bytes anywhere."""
    z = zipfile.ZipFile(io.BytesIO(wheel))
    return _zip({n: z.read(n) for n in z.namelist()
                 if not n.startswith("pdfminer/cmap/") and not n.endswith(".dist-info/RECORD")})


def fetch_runtime() -> None:
    """Download the pinned runtime into docs/, checking every digest on the
    way. Files already there and matching their pin are kept."""
    import json
    import tarfile
    from urllib.request import urlopen

    def get(url, sha256=None):
        data = urlopen(url, timeout=120).read()
        if sha256 and _sha256(data) != sha256:
            raise SystemExit(f"{url} does not match its published digest")
        return data

    (DOCS / "pyodide").mkdir(parents=True, exist_ok=True)
    npm = [p for p in RUNTIME if p.startswith("pyodide/") and p != "pyodide/LICENSE"
           and not p.endswith(".whl")]
    if not all(map(_pinned, npm)):
        tarball = urlopen(PYODIDE_TARBALL[0], timeout=300).read()
        if hashlib.sha512(tarball).hexdigest() != PYODIDE_TARBALL[1]:
            raise SystemExit("The Pyodide tarball does not match its npm integrity digest")
        with tarfile.open(fileobj=io.BytesIO(tarball)) as t:
            for p in npm:
                (DOCS / p).write_bytes(t.extractfile("package/" + p.split("/", 1)[1]).read())
    if not _pinned("pyodide/LICENSE"):
        (DOCS / "pyodide/LICENSE").write_bytes(
            get("https://raw.githubusercontent.com/pyodide/pyodide/main/LICENSE"))
    lock = json.loads((DOCS / "pyodide/pyodide-lock.json").read_bytes())["packages"]
    wanted = {lock[n]["file_name"]: lock[n]["sha256"] for n in (*UNLOCK, *READ_PDF)
              if not _pinned(f"pyodide/{lock[n]['file_name']}")}
    if wanted:
        with urlopen(PYODIDE_RELEASE, timeout=1800) as r, tarfile.open(fileobj=r, mode="r|bz2") as t:
            for m in t:  # 340 MB, streamed: only the wheels wanted are kept
                name = m.name.rsplit("/", 1)[-1]
                if name in wanted:
                    data = t.extractfile(m).read()
                    if _sha256(data) != wanted.pop(name):
                        raise SystemExit(f"{name} does not match pyodide-lock.json")
                    (DOCS / "pyodide" / name).write_bytes(data)
                    if not wanted:
                        break
    if wanted:
        raise SystemExit(f"Not in the Pyodide release: {sorted(wanted)}")
    (DOCS / "vendor").mkdir(exist_ok=True)
    path, project, version = PDF_READER
    if not _pinned(path):
        meta = json.load(urlopen(f"https://pypi.org/pypi/{project}/{version}/json", timeout=60))
        [u] = [u for u in meta["urls"] if u["filename"] == f"pdfminer_six-{version}-py3-none-any.whl"]
        (DOCS / path).write_bytes(pdf_reader_zip(get(u["url"], u["digests"]["sha256"])))
    for p, project in PACKAGES.items():
        if _pinned(p):
            continue
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
