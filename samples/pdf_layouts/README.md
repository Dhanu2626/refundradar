# PDF layouts (synthetic data)

The HDFC and SBI statements of `../realistic/`, drawn as PDFs the ways report writers
draw tables, and a few PDFs the reader must refuse. Every page says it is synthetic at
its top; the scans are a picture of grey bars, the second with the synthetic HDFC rows
(and that line) hidden under it as a scanner's invisible text. Written by `tools/make_realistic_statements.py` (`LAYOUTS`); read by
`tests/test_pdf.py`. The PDF reader is `refundradar/pdftable.py` (DECISIONS.md, D18).

Read exactly as the spreadsheet, every field:

| File | How it is drawn |
|---|---|
| `hdfc_breaks_after_hyphens.pdf`, `sbi_breaks_after_hyphens.pdf` | Wrapped lines break after a hyphen or slash, as well as at spaces |
| `hdfc_heading_on_first_page_only.pdf` | Page 2 carries on without the table's heading |
| `hdfc_rows_split_by_page_breaks.pdf` | A transaction's last lines carry over to the next page |
| `hdfc_words_drawn_apart.pdf` | Each word placed on its own: gaps, no space characters |
| `hdfc_courier.pdf` | A fixed-width font, in which dates and references wrap too |
| `hdfc_heading_drawn_twice.pdf` | The heading drawn twice as fake bold, its cells centred |
| `hdfc_newest_first.pdf` | Newest transaction first |
| `sbi_times.pdf` | Times, a larger size |

Read exactly except where a space fell on a line break (a PDF doesn't record it, so
"SAMPLE FRIEND" can read "SAMPLEFRIEND"); dates, amounts, balances, references and
channels are exact:

| File | How it is drawn |
|---|---|
| `hdfc_breaks_anywhere.pdf`, `sbi_breaks_anywhere.pdf` | Lines filled to the edge, broken at any character |
| `sbi_rows_split_by_page_breaks.pdf` | A transaction carried over to the next page, larger type |
| `sbi_words_drawn_apart.pdf` | Words placed on their own, heading on page 1 only |

Refused, naming why and where:

| File | Why |
|---|---|
| `hdfc_rows_centred.pdf`, `hdfc_rows_bottom_aligned.pdf`, `sbi_rows_centred.pdf` | Cells centred or bottom-aligned in their row put a transaction's first lines above its date |
| `hdfc_amount_misprinted.pdf` | One payment printed 1,463.00: the running balance doesn't add up |
| `hdfc_note_between_rows.pdf` | A line of text between two transactions that belongs to neither |
| `hdfc_row_after_summary.pdf` | A transaction printed after the STATEMENT SUMMARY |
| `other_bank.pdf` | A table laid out the way neither SBI nor HDFC lays one out |
| `scanned.pdf`, `scanned_with_hidden_text.pdf` | A picture of a statement, with and without a scanner's invisible text |

They prove the reader against the ways of drawing a table listed here, not against a
bank's real PDF: none has been read yet.
