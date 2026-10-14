"""Command line interface for the skuv SKU list validator.

Pipeline: read (readers) -> validate (validators) -> write (report).
Exit-code contract: 0 = no invalid rows, 1 = at least one invalid row,
2 = usage/input/output error (message on stderr, no reports written).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .readers import InputError, read_rows
from .report import write_reports
from .validators import find_duplicates, validate_row

DEFAULT_OUTDIR = "out"


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the skuv CLI."""
    parser = argparse.ArgumentParser(
        prog="skuv",
        description="Validate a SKU list (.csv or .xlsx) and write cleaned reports.",
    )
    parser.add_argument(
        "input",
        metavar="INPUTFILE",
        help="SKU list to validate (.csv or .xlsx)",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        default=DEFAULT_OUTDIR,
        help="output directory (default: %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the validator. Returns the process exit code (0, 1 or 2)."""
    args = build_parser().parse_args(argv)

    try:
        rows = read_rows(args.input)
    except InputError as exc:
        print("skuv: error: " + str(exc), file=sys.stderr)
        return 2

    duplicates = find_duplicates(rows)
    results = [validate_row(row, duplicates) for row in rows]

    try:
        write_reports(results, args.outdir)
    except OSError as exc:
        print("skuv: error: cannot write reports to " + str(args.outdir) + ": " + str(exc), file=sys.stderr)
        return 2

    return 1 if any(not result.is_valid for result in results) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
