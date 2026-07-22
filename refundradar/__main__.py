"""Run RefundRadar from the command line.

  python -m refundradar serve            start the web app on http://127.0.0.1:8626
  python -m refundradar audit FILE.csv   audit a statement in the terminal
  python -m refundradar demo             audit the built-in synthetic statement
"""

import argparse
import json
import sys
from pathlib import Path

from refundradar.audit import build_audit
from refundradar.complaint import generate_complaint_pack
from refundradar.parser import parse_generic_csv
from refundradar.reconcile import LATE, NEVER

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _print_audit(csv_path: Path, confirmed: set[str]) -> None:
    txns = parse_generic_csv(csv_path)
    a = build_audit(txns, confirmed)
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="refundradar")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    ap = sub.add_parser("audit")
    ap.add_argument("file", type=Path)
    ap.add_argument("--confirm", action="append", default=[],
                    help="reference of a payment you know failed (repeatable)")
    sub.add_parser("demo")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn
        print("RefundRadar running — open http://127.0.0.1:8626 in your browser")
        uvicorn.run("refundradar.webapp:app", host="127.0.0.1", port=8626)
    elif args.cmd == "audit":
        _print_audit(args.file, set(args.confirm))
    elif args.cmd == "demo":
        truth = json.loads((SAMPLES / "ground_truth.json").read_text())
        confirmed = {i["ref"] for i in truth["incidents"]
                     if i["is_incident"] and i["refund_date"] is None}
        _print_audit(SAMPLES / "demo_statement.csv", confirmed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
