# Realistic statements (synthetic data)

Statements laid out the way SBI's and HDFC's own downloads are, filled with made-up
data. Every file says so at its top (HDFC's just under the bank's name), and every PDF
on every page. Written by
`tools/make_realistic_statements.py`, which lists the planted cases; checked by
`tests/test_realistic_statements.py`.

| File | What it imitates |
|---|---|
| `hdfc_netbanking.xls` | HDFC NetBanking's Excel download: customer block, asterisk rules, STATEMENT SUMMARY, footer |
| `hdfc_netbanking_saved_as.csv` | The same file saved as CSV by an Indian-locale Excel (`1,23,456.00`) |
| `hdfc_delimited.txt` | HDFC's Delimited download: the table only, space-padded, a narration with a comma in it |
| `sbi_account_statement.xlsx` | SBI's account statement as OnlineSBI heads it (Txn Date ... Branch Code) |
| `sbi_account_statement_locked.xlsx` | The same, password-protected like SBI's download. Password: `54321150690` |
| `sbi_details_layout.xlsx` | The same, headed Date / Details as the July 2026 field-tested download was |
| `hdfc_netbanking.pdf` | HDFC's statement as a PDF: page head on every page, customer block, a table without rules, STATEMENT SUMMARY, the bank's footer |
| `sbi_account_statement.pdf` | SBI's account statement as a PDF: account block, a ruled grid, dates in a column narrow enough to wrap |
| `sbi_account_statement_locked.pdf` | The same, locked with AES-256 like SBI's e-statement. Password: `54321150690` |

Each PDF reads exactly as its spreadsheet twin, every transaction and every field
(`tests/test_pdf.py`); `../pdf_layouts/` draws the same statements other ways. Drop any
of them on the live page to see a whole audit. They test the readers against
the layouts as known; they are not a real bank's file, so they cannot prove a layout
nobody has sent us yet.
