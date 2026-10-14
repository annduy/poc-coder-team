"""Command line interface for the skuv SKU list validator.

M1 stage: the CLI contract only. The read -> validate -> write pipeline is a
stub here; readers (M2), validators (M3) and the report writer (M4) follow.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    parser = build_parser()
    args = parser.parse_args(argv)

    path = Path(args.input)
    if not path.is_file():
        print("skuv: error: input file not found: " + str(path), file=sys.stderr)
        return 2

    # TODO(M2): read rows. TODO(M3): validate rows. TODO(M4): write reports.
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
