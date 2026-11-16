"""Command line: python -m app.evals termsheets | copilot [options]."""

import argparse
import sys

from app.evals import copilot, termsheets


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evals", description=__doc__)
    sub = parser.add_subparsers(dest="which", required=True)
    ts = sub.add_parser("termsheets", help="offline check of the term sheet rules")
    ts.add_argument(
        "--min", type=float, default=0.95, help="fail below this accuracy (default 0.95)"
    )
    cp = sub.add_parser("copilot", help="ask the running Copilot the fixed questions")
    cp.add_argument("--base-url", default="http://localhost:8001")
    cp.add_argument("--user", default="anna.syndicate")
    cp.add_argument("--password", required=True)
    cp.add_argument(
        "--min", type=float, default=0.8, help="fail below this pass rate (default 0.8)"
    )
    args = parser.parse_args()

    if args.which == "termsheets":
        results = termsheets.run()
        print(termsheets.report(results))
        return 0 if termsheets.accuracy(results) >= args.min else 1
    outcomes = copilot.run(args.base_url, args.user, args.password)
    print(copilot.report(outcomes))
    return 0 if sum(o.passed for o in outcomes) / len(outcomes) >= args.min else 1


if __name__ == "__main__":
    sys.exit(main())
