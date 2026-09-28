"""Rebuild a statement PDF's transaction table as rows (DECISIONS.md, D18).

A PDF has no rows or cells, only characters placed on pages. This finds SBI's
or HDFC's own table heading, takes the columns from the gaps no character
crosses, and puts each transaction's lines (a wrapped description, a wrapped
date) back into one row. The rows then go through the same strict readers as
a spreadsheet, running balance included. Whatever can't be placed with
certainty stops the audit, naming the page, instead of being guessed at: a
scanned page, text drawn as unreadable codes, a line that belongs to no
transaction.

Built from the layouts as known and synthetic PDFs drawn like them: no real
SBI or HDFC PDF has been through it yet.
"""

import io
import re
from bisect import bisect
from dataclasses import dataclass
from statistics import median

from refundradar.formats import EncryptedStatement, WrongPassword, _cell_date
from refundradar.model import _RRN, _UTR16
from refundradar.parser import NO_BANK_TABLE, _hdfc_columns, _sbi_columns

LOCKED = ("This PDF is password-protected by your bank. It opens with the password the "
          "bank set for the file (its statement page or email says how that password is "
          "made), not your login password.")
WRONG_PASSWORD = ("That password doesn't open this PDF. Use the password your bank set "
                  "for the file (its statement page or email says how it is made), not "
                  "your login password.")
SCANNED = ("This PDF has no readable text: it is a scan or a photo of a statement. "
           "RefundRadar reads the PDF your bank's website or email gives you, where the "
           "numbers are text; reading them off a picture could misread an amount. "
           "Download the statement from net banking as PDF, Excel or CSV.")
CODES = ("This PDF's text comes out as codes instead of letters (its fonts don't say "
         "which characters they draw), so it can't be read reliably. Download the "
         "statement from net banking again, as Excel or CSV if the bank offers it.")
DAMAGED = "This PDF is damaged or incomplete, so it can't be read. Download it again."

# a date as the first thing in the date column: 01/06/26, 1 Jun 2026, 2026-06-01,
# or the start of one the column wrapped (12 Jun, 01/06/2); the reader checks the whole date
_DATE_START = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}([/.-]\d{1,2}([/.-]|$)|[ -][A-Za-z]{3,9}\b)")
_AMOUNT = re.compile(r"[-+]?\d[\d,]*\.\d{2}")
_PAGE_NO = re.compile(r"page\b.*\d|\d+\s*(of|/)\s*\d+", re.I)


@dataclass
class _Char:
    text: str
    x0: float
    x1: float
    y: float     # baseline; larger is higher on the page
    size: float


@dataclass
class _Line:
    page: int    # 1-based
    no: int      # 1-based, top of the page first
    y: float
    size: float
    chars: list  # left to right, spaces included


@dataclass
class _Piece:
    """One line of one cell."""
    text: str
    x1: float     # where its last character ends
    first: float  # width of its first character
    spaced: bool  # a space inside it


# The first line of the rows handed back as CSV (webapp, D18): later steps
# read the rows, not the PDF, and still say the statement came from one.
MARK = "RefundRadar: transactions read from a PDF statement"


class PdfRows(list):
    """Rows rebuilt from a PDF, each knowing where on which page it was read,
    so a reader's "Row 45" can become "Page 2, row 7"."""

    def __init__(self, rows, places, locked=False):
        super().__init__(rows)
        self.places = places
        self.locked = locked  # it took a password to open

    def as_csv(self) -> bytes:
        """The rows as CSV, headed by MARK: the same rows, so the same
        transactions, without the PDF or its password."""
        import csv
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow([MARK])
        writer.writerows(self)
        return out.getvalue().encode("utf-8")

    def explain(self, message: str) -> str:
        def place(m):
            where = self.places.get(int(m.group(2)) - 1)
            if where is None:
                return m.group(0)
            return where[0].upper() + where[1:] if m.group(1) == "Row" else where
        return re.sub(r"\b(Row|row) (\d+)\b", place, message)


# --- characters -------------------------------------------------------------

def _pages(data: bytes, password: str | None) -> tuple[list[list[_Char]], bool]:
    """Every visible, upright character of every page, and whether the file
    was locked."""
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.layout import LTChar
    from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError, PDFPasswordIncorrect
    from pdfminer.pdffont import PDFUnicodeNotDefined
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.psexceptions import PSException

    class Collector(PDFLayoutAnalyzer):
        hidden = False

        def begin_page(self, page, ctm):
            super().begin_page(page, ctm)
            self.chars = []

        def end_page(self, page):
            self.pages.append(self.chars)

        def render_string(self, textstate, seq, ncs, graphicstate):
            self.hidden = textstate.render in (3, 7)  # invisible, as over a scan
            super().render_string(textstate, seq, ncs, graphicstate)

        def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
            try:
                text = font.to_unichr(cid)
            except PDFUnicodeNotDefined:
                text = f"(cid:{cid})"
            c = LTChar(matrix, font, fontsize, scaling, rise, text, font.char_width(cid),
                       font.char_disp(cid), ncs, graphicstate)
            if not self.hidden and c.upright and text:
                self.chars.append(_Char(text, c.x0, c.x1, matrix[5], c.size))
            return c.adv

        def paint_path(self, *args):
            pass  # rules and boxes: the columns come from the text itself

        def render_image(self, name, stream):
            pass

    locked = False
    try:
        try:  # a PDF locked only against editing opens without a password
            doc = PDFDocument(PDFParser(io.BytesIO(data)), password="")
        except PDFPasswordIncorrect:
            if not password:
                raise EncryptedStatement(LOCKED) from None
            locked = True
            try:
                doc = PDFDocument(PDFParser(io.BytesIO(data)), password=password)
            except PDFPasswordIncorrect:
                raise WrongPassword(WRONG_PASSWORD) from None
    except PDFEncryptionError:
        raise ValueError("This PDF is locked in a way RefundRadar can't open. Download "
                         "the statement from net banking again.") from None
    except (PSException, ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise ValueError(DAMAGED) from None
    rsrc = PDFResourceManager()
    device = Collector(rsrc)
    device.pages = []
    interpreter = PDFPageInterpreter(rsrc, device)
    try:
        for page in PDFPage.create_pages(doc):
            interpreter.process_page(page)
    except (PSException, ValueError, KeyError, TypeError, AttributeError, IndexError):
        raise ValueError(DAMAGED) from None
    return device.pages, locked


def _lines(pages: list[list[_Char]]) -> list[_Line]:
    """Characters grouped into lines by baseline, top to bottom, each line's
    characters left to right, with text drawn twice (fake bold) kept once."""
    out = []
    for n, chars in enumerate(pages, 1):
        rows = []
        for c in sorted(chars, key=lambda c: (-c.y, c.x0)):
            if rows and abs(rows[-1][0].y - c.y) <= 0.3 * max(c.size, rows[-1][0].size):
                rows[-1].append(c)
            else:
                rows.append([c])
        for no, row in enumerate(rows, 1):
            row.sort(key=lambda c: c.x0)
            kept = []
            for c in row:
                if not any(k.text == c.text and abs(k.x0 - c.x0) < 0.3 * (c.x1 - c.x0 or 1)
                           for k in kept[-3:]):
                    kept.append(c)
            out.append(_Line(n, no, median(c.y for c in kept), median(c.size for c in kept),
                             kept))
    return out


def _words(chars: list[_Char], size: float) -> list[list[_Char]]:
    """Runs of characters with no space and no gap between them."""
    words, word = [], []
    for c in chars:
        if c.text.isspace():
            if word:
                words.append(word)
            word = []
            continue
        if word and c.x0 - word[-1].x1 > 0.15 * size:
            words.append(word)
            word = []
        word.append(c)
    return words + ([word] if word else [])


def _text(words) -> str:
    return " ".join("".join(c.text for c in w) for w in words)


# --- the heading ------------------------------------------------------------

def _heading_cells(block: list[_Line]):
    """[text, x0, x1] cells of a table heading drawn over one or more lines."""
    cells = []
    for i, line in enumerate(block):
        words = _words(line.chars, line.size)
        spaces = [c.x1 - c.x0 for c in line.chars if c.text == " " and c.x1 > c.x0]
        space = median(spaces) if spaces else 0.3 * line.size
        pieces = []
        for w in words:  # words a space apart are one cell; a wider gap starts another
            if pieces and w[0].x0 - pieces[-1][-1][-1].x1 <= 1.5 * space:
                pieces[-1].append(w)
            else:
                pieces.append([w])
        for p in pieces:
            text, x0, x1 = _text(p), p[0][0].x0, p[-1][-1].x1
            over = [(min(x1, c[2]) - max(x0, c[1]), c) for c in cells]
            over = [(o, c) for o, c in over if o > 0]
            if i and len(over) > 1:
                return None  # one piece under two cells: not a wrapped heading
            if over:
                c = over[0][1]
                c[0], c[1], c[2] = f"{c[0]} {text}", min(c[1], x0), max(c[2], x1)
            else:
                cells.append([text, x0, x1])
    return sorted(cells, key=lambda c: c[1])


def _match(cells):
    names = [c[0] for c in cells]
    return _hdfc_columns(names) or _sbi_columns(names)


def _heading(lines: list[_Line], start: int, depth: int | None = None):
    """(index after the heading, cells, columns) for a heading starting at
    lines[start], or None. A heading may wrap onto three lines; the lines
    under it that only finish its cells ("Amt.", "Balance") are part of it.
    With `depth`, only a heading of exactly that many lines: the first
    page's, repeated, whose next line may be a split row's end."""
    def tight(a, b):
        return a.page == b.page and a.y - b.y <= 1.6 * max(a.size, b.size)

    def plain(line):  # a heading has no figures in it
        return not any(c.text.isdigit() for c in line.chars)

    found = None
    for k in ((depth,) if depth else (1, 2, 3)):
        block = lines[start:start + k]
        if len(block) < k or not plain(block[-1]) or (k > 1 and not tight(block[-2], block[-1])):
            break
        cells = _heading_cells(block)
        cols = cells and _match(cells)
        if cols:
            found = (start + k, cells, cols)
            break
    if found is None:
        return None
    end, cells, cols = found
    while not depth and end < len(lines) and plain(lines[end]) and tight(lines[end - 1], lines[end]):
        more = _heading_cells(lines[start:end + 1])
        if not more or len(more) != len(cells) or _match(more) != cols:
            break
        end, cells = end + 1, more
    return end, cells, cols


# --- rows -------------------------------------------------------------------

def _bounds(cells, lines: list[_Line]) -> list[float]:
    """Where one column ends and the next begins: in the widest gap between
    two headings' centres that no character of the table crosses."""
    spans = [(c.x0, c.x1) for line in lines for c in line.chars if not c.text.isspace()]
    spans += [(c[1], c[2]) for c in cells]
    spans.sort()
    bounds = []
    for a, b in zip(cells, cells[1:]):
        lo, hi = (a[1] + a[2]) / 2, (b[1] + b[2]) / 2
        best, edge = None, lo
        for x0, x1 in spans:
            if x1 <= edge:
                continue
            if x0 >= hi:
                break
            if x0 > edge and (best is None or x0 - edge > best[1] - best[0]):
                best = (edge, x0)
            edge = max(edge, x1)
        if edge < hi and (best is None or hi - edge > best[1] - best[0]):
            best = (edge, hi)
        if best is None or best[1] - best[0] < 0.5:
            raise ValueError(
                f"The columns {a[0]!r} and {b[0]!r} of this PDF's table run into each "
                "other, so which text belongs to which can't be told apart.")
        bounds.append((best[0] + best[1]) / 2)
    return bounds


def _cells(line: _Line, bounds, n: int) -> list[list]:
    """The line's characters, column by column (by each character's centre)."""
    out = [[] for _ in range(n)]
    for c in line.chars:
        out[bisect(bounds, (c.x0 + c.x1) / 2)].append(c)
    return out


def _piece(chars, size) -> _Piece | None:
    words = _words(chars, size)
    if not words:
        return None
    return _Piece(_text(words), words[-1][-1].x1, words[0][0].x1 - words[0][0].x0, len(words) > 1)


def _starts_row(line: _Line, lo: float, hi: float) -> bool:
    """Whether the line has a date under the date heading (between the
    headings either side of it), as a transaction's first line does."""
    words = [w for w in _words(line.chars, line.size) if lo <= (w[0].x0 + w[-1].x1) / 2 < hi]
    return bool(words) and bool(_DATE_START.match(_text(words)))


def _amounts(line: _Line, bounds, n: int, money_cols) -> bool:
    cells = _cells(line, bounds, n)
    return any(_AMOUNT.fullmatch("".join(c.text for c in w))
               for i in money_cols for w in _words(cells[i], line.size))


def _refs(text: str) -> set:
    return set(_RRN.findall(text)) | set(_UTR16.findall(text.upper()))


def _join(pieces: list[_Piece], limit: float, filled: bool) -> str:
    """A wrapped cell's lines as the one string the bank wrote.

    A PDF doesn't say whether a line broke at a space or inside a word, and a
    wrongly inserted space can split a 12-digit reference in two. Report
    writers break lines at spaces, and inside a word only when the word is
    longer than a whole line. So a line that stopped short of the column's
    edge by more than the next character broke at a space, and so did one
    with a space on it; any other line that reached the edge broke inside a
    word, unless joining it would swallow a reference ("CHARGES" then
    "616012345603"). After a word ending in a hyphen or slash nothing is
    added. When the lines of a column are all filled to the edge, the text
    was broken anywhere, and lines are joined as they are. Either way a space
    that fell exactly on a break can be lost: no PDF records it.
    """
    text = pieces[0].text
    for prev, nxt in zip(pieces, pieces[1:]):
        if prev.text.endswith(("-", "/")) and not prev.text[:-1].endswith(" "):
            gap = ""
        elif limit - prev.x1 >= nxt.first - 0.01:
            gap = " "  # the next character would have fitted: a break at a space
        elif filled:
            gap = ""
        elif prev.spaced:
            gap = " "
        else:
            gap = ""
            if (not (prev.text[-1].isdigit() and nxt.text[0].isdigit())
                    and _refs(prev.text + " " + nxt.text) - _refs(prev.text + nxt.text)):
                gap = " "  # e.g. CHARGES / 616012345603: keep the reference whole
        text += gap + nxt.text
    return text


def pdf_rows(data: bytes, password: str | None = None) -> PdfRows:
    """The statement table of a PDF, as the rows a spreadsheet would hold:
    the lines above the table, its heading, then one row per transaction."""
    pages, locked = _pages(data, password)
    if not pages:
        raise ValueError(DAMAGED)
    chars = [c for page in pages for c in page if not c.text.isspace()]
    if not chars:
        raise ValueError(SCANNED)
    if sum("(cid:" in c.text for c in chars) > 0.02 * len(chars):
        raise ValueError(CODES)
    lines = _lines(pages)

    first = next(((i, h) for i in range(len(lines)) if (h := _heading(lines, i))), None)
    if first is None:
        raise ValueError(NO_BANK_TABLE)
    start, (body, cells, cols) = first
    names = [c[0] for c in cells]
    n, date_col, text_col = len(cells), cols["date"], cols["narration"]
    money = [cols[k] for k in ("debit", "credit", "balance")]

    # each page's own copy of the heading, when it repeats it
    headed = {lines[start].page: (start, body)}
    i = body
    while i < len(lines):
        h = _heading(lines, i, body - start) if lines[i].page not in headed else None
        if h and [c[0] for c in h[1]] != names:
            raise ValueError(
                f"Page {lines[i].page} starts a different table "
                f"({' / '.join(c[0] for c in h[1])}). Audit each statement on its own.")
        if h:
            headed[lines[i].page] = (i, h[0])
        i = h[0] if h else i + 1
    # a line with no letter or figure (a rule of asterisks or dashes) holds
    # nothing to read: passed over, as the spreadsheet readers pass it over
    table = [j for j in range(body, len(lines))
             if (lines[j].page not in headed or j >= headed[lines[j].page][1])
             and any(c.text.isalnum() for c in lines[j].chars)]

    # a date under the date heading starts a transaction; the lines under it,
    # as close as a wrapped cell's lines are to each other, finish it
    lo = cells[date_col - 1][2] if date_col else float("-inf")
    hi = cells[date_col + 1][1] - 0.5 if date_col + 1 < n else float("inf")
    # HDFC's STATEMENT SUMMARY ends the table: below it, only its totals may
    # follow, which the reader checks (a dated row with an amount stops it)
    summary = next((j for j in table if "statement summary" in _text(
        _words(lines[j].chars, lines[j].size)).lower()), len(lines))
    starts = {j for j in table if j < summary and _starts_row(lines[j], lo, hi)}
    if not starts:
        raise ValueError(
            "Found the statement's table heading in this PDF but no transactions under it.")
    first_on, last_on = {}, {}
    for j in sorted(starts):
        first_on.setdefault(lines[j].page, j)
        last_on[lines[j].page] = j
    steps = [lines[a].y - lines[b].y for a, b in zip(table, table[1:])
             if lines[a].page == lines[b].page and b not in starts
             and first_on.get(lines[b].page, len(lines)) <= a < b < last_on.get(lines[b].page, -1)]
    pitch = median(steps) if steps else 1.3 * median(lines[j].size for j in starts)

    # the columns, from the gaps the transactions' own lines leave: a footer
    # or a note running across the page doesn't get a say
    rowish, prev = list(range(start, body)), None
    for j in table:
        line = lines[j]
        if j >= summary:
            break
        if j in starts or first_on.get(line.page, len(lines)) < j < last_on.get(line.page, -1):
            rowish.append(j)
            prev = line
        elif prev is not None and prev.page == line.page and prev.y - line.y <= 1.45 * pitch:
            rowish.append(j)
            prev = line
        else:
            prev = None
    bounds = _bounds(cells, [lines[j] for j in rowish])
    for j in rowish:  # no word may be cut in two by a column edge
        line = lines[j]
        for w in _words(line.chars, line.size):
            if bisect(bounds, (w[0].x0 + w[0].x1) / 2) != bisect(bounds, (w[-1].x0 + w[-1].x1) / 2):
                raise ValueError(
                    f"Page {line.page}, line {line.no}: {_text([w])!r} runs across two of "
                    "the table's columns, so which text belongs to which can't be told apart.")

    rows = [[_text(_words(line.chars, line.size))] for line in lines[:start]] + [names]
    places, pieces = {}, {}  # row index -> where it was read; -> its cells' lines
    count_on = {}
    current = None   # row index of the transaction being read
    last = None      # the last line read into it
    open_cols = set()  # the columns whose text can carry on to the next line
    open_on = None   # the page it may still continue on
    after_summary = False
    table_end = None  # where the rows after HDFC's summary begin

    def carry_on(cells_, cols_):
        """Of the columns a line had text in, those a wrapped cell can
        carry on from: never an amount (amounts don't wrap), never a
        column already holding a whole date (a footer under the last row
        is not part of it). A date cut short ("12 Jun") may carry on."""
        def whole_date(text):
            return len(text) <= 20 and any(ch.isdigit() for ch in text) and _cell_date(text)
        return {col for col in cols_ if cells_[col] and col not in money
                and not whole_date(" ".join(p.text for p in cells_[col]))}

    def emit(j):
        line = lines[j]
        rows.append([(p.text if (p := _piece(c, line.size)) else "")
                     for c in _cells(line, bounds, n)])
        places[len(rows) - 1] = f"page {line.page}, line {line.no}"

    for j in table:
        line = lines[j]
        text = _text(_words(line.chars, line.size))
        if j == summary:
            after_summary, current, table_end = True, None, len(rows)
            rows.append([text])  # whole: it runs across the columns
            places[len(rows) - 1] = f"page {line.page}, line {line.no}"
            continue
        if after_summary:
            emit(j)  # the reader checks that nothing but totals follow
            continue
        cells_ = _cells(line, bounds, n)
        if j in starts:
            count_on[line.page] = count_on.get(line.page, 0) + 1
            rows.append(None)
            current, last, open_on = len(rows) - 1, line, line.page
            pieces[current] = [[p] if (p := _piece(c, line.size)) else [] for c in cells_]
            open_cols = carry_on(pieces[current], range(n))
            places[current] = f"page {line.page}, row {count_on[line.page]}"
            continue
        if _amounts(line, bounds, n, money):
            current = None
            emit(j)  # an amount with no date: the reader decides, it is never dropped
            continue
        before_first = line.page in first_on and j < first_on[line.page]
        used = {col for col, c in enumerate(cells_) if _piece(c, line.size)}
        if current is not None and used <= open_cols and not _PAGE_NO.fullmatch(text) \
                and abs(line.size - last.size) <= 0.15 * last.size and (
                (line.page == open_on and last.y - line.y <= 1.45 * pitch)
                # a row the page break split, finished under the next page's heading
                or (line.page != last.page and line.page in headed
                    and j < first_on.get(line.page, len(lines)))):
            for col in used:
                pieces[current][col].append(_piece(cells_[col], line.size))
            last, open_on = line, line.page
            open_cols = carry_on(pieces[current], used)
            continue
        if current is not None and text_col in used and not pieces[current][text_col] and (
                line.page == last.page and last.y - line.y <= 1.45 * pitch):
            raise ValueError(
                f"{places[current][0].upper()}{places[current][1:]}: its description "
                "starts below its date. RefundRadar reads a transaction's lines from the "
                "line with its date down, and this PDF isn't laid out that way.")
        inside = first_on.get(line.page, len(lines)) < j < last_on.get(line.page, -1)
        if inside or (before_first and line.page == lines[start].page):
            raise ValueError(
                f"Page {line.page}, line {line.no}: {text!r} sits in the table without "
                "belonging to a transaction. Stopping rather than guessing which "
                "transaction it is part of.")
        open_on = None  # page furniture: a page number, a footer, a note under the table

    # a wrapped cell's lines back into one string, column by column
    for col in range(n):
        wraps = [(a, b) for cell in pieces.values() for a, b in zip(cell[col], cell[col][1:])]
        limit = max((p.x1 for cell in pieces.values() for p in cell[col]), default=0)
        # broken anywhere: lines with a space on them still run to the edge
        spaced = [(a, b) for a, b in wraps if a.spaced]
        filled = len(spaced) >= 4 and sum(limit - a.x1 < b.first - 0.01
                                           for a, b in spaced) >= 0.6 * len(spaced)
        for cell in pieces.values():
            cell[col] = _join(cell[col], limit, filled) if cell[col] else ""
    for idx, cell in pieces.items():
        rows[idx] = cell
    # codes in the table itself (not in a footer after the summary) can't be read
    if any("(cid:" in c for r in rows[start:table_end] for c in r):
        raise ValueError(CODES)
    return PdfRows(rows, places, locked)
