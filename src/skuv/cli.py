"""Command line interface for the skuv SKU list validator.

Pipeline: read -> validate -> write (readers land in M2, validators in M3 and
the report writer in M4; the stages below are wired as they arrive).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .readers import InputError, read_rows

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

    # TODO(M3): validate rows. TODO(M4): write reports.
    print("read " + str(len(rows)) + " row(s) from " + str(args.input))
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
