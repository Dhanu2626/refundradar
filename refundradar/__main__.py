"""Run RefundRadar from the command line.

  python -m refundradar serve            start the web app on http://127.0.0.1:8626
  python -m refundradar audit FILE.csv   audit a statement in the terminal
  python -m refundradar demo             audit the built-in synthetic statement
"""

import argparse
import sys
from pathlib import Path

from refundradar.audit import build_audit
from refundradar.formats import EncryptedStatement
from refundradar.parser import parse_statement_file
from refundradar.reconcile import LATE, NEVER, can_confirm_failed, has_reference

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _confirmed_rows(txns, numbers: list[int]):
    """The payments printed without a reference that you said failed, by
    their transaction number (1 is the statement's first), as the web app
    shows them (D14)."""
    chosen = []
    for n in numbers:
        t = txns[n - 1] if 1 <= n <= len(txns) else None
        if t is None or has_reference(t) or not can_confirm_failed(t):
            raise ValueError(f"--confirm-row {n}: transaction {n} is not a payment printed "
                             "without a reference. Payments with one are confirmed with --confirm.")
        chosen.append(t)
    return chosen


def _print_audit(csv_path: Path, confirmed: set[str], password: str | None = None,
                 rows: list[int] = ()) -> None:
    txns = parse_statement_file(csv_path, password=password)
    chosen = _confirmed_rows(txns, rows)
    a = build_audit(txns, confirmed, confirmed_failed_txns=chosen)
    print(f"RefundRadar audit of {csv_path.name} — {a.statement_lines} lines, "
          f"as of {a.as_of.isoformat()}")
    print(f"  Total owed to you : Rs.{a.total_owed_inr}")
    print(f"  Stuck refunds     : Rs.{a.stuck_amount}")
    print(f"  Refunds on time   : {a.on_time_count}")
    for i in a.incidents:
        flag = "!!" if i.status in (LATE, NEVER) else "  "
        comp = f" -> Rs.{i.ruling.compensation_inr}" if i.ruling else ""
        print(f"  {flag} [{i.status}] {i.txn.txn_date} Rs.{i.txn.amount} "
              f"({i.txn.channel}){comp}")
        print(f"       {i.reason}")
    # the statement can't show a failure that was never reversed: only you can say so
    findings = {id(i.txn) for i in a.incidents}
    no_ref = [(n, t) for n, t in enumerate(txns, 1)
              if can_confirm_failed(t) and not has_reference(t) and id(t) not in findings]
    if no_ref:
        print("  Printed without a reference (if one of these failed and never came back, "
              "add --confirm-row N):")
        for n, t in no_ref:
            print(f"     transaction {n}: {t.txn_date} Rs.{t.amount}  {t.narration[:60]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="refundradar")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    ap = sub.add_parser("audit")
    ap.add_argument("file", type=Path)
    ap.add_argument("--confirm", action="append", default=[],
                    help="reference of a payment you know failed (repeatable)")
    ap.add_argument("--confirm-row", action="append", type=int, default=[], metavar="N",
                    help="transaction N, a payment printed without a reference, that you "
                         "know failed (repeatable)")
    ap.add_argument("--password", default=None,
                    help="document password for bank-protected statements")
    sub.add_parser("demo")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn
        print("RefundRadar running — open http://127.0.0.1:8626 in your browser")
        uvicorn.run("refundradar.webapp:app", host="127.0.0.1", port=8626)
    elif args.cmd == "audit":
        try:
            _print_audit(args.file, set(args.confirm), password=args.password,
                         rows=args.confirm_row)
        except EncryptedStatement as e:
            print(f"Locked file: {e}")
            return 1
        except ValueError as e:
            print(f"Could not audit {args.file.name}: {e}")
            return 1
        except Exception as e:  # never a traceback: say what failed, claim nothing
            print(f"Could not audit {args.file.name}: {type(e).__name__}: {e}")
            return 1
    elif args.cmd == "demo":
        # the synthetic sample, audited like any statement: nothing answered for you
        _print_audit(SAMPLES / "demo_statement.csv", set())
        print("  A failed payment that never came back looks like any other payment on a "
              "statement. If you know one failed, confirm it:\n"
              "     python -m refundradar audit samples/demo_statement.csv --confirm <reference>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
