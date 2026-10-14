"""skuv - SKU list validator CLI (PoC-1).

Validates SKU lists (ean, description, optional price) delivered as .csv or
.xlsx and writes cleaned output plus an error report.
"""

from .readers import InputError, RawRow, read_rows
from .report import write_reports
from .validators import (
    ERROR_CODES,
    ISSUE_CODES,
    Issue,
    RowResult,
    find_duplicates,
    gs1_check_ok,
    parse_price,
    validate_description,
    validate_ean,
    validate_row,
)

__version__ = "0.1.0"

__all__ = [
    "ERROR_CODES",
    "ISSUE_CODES",
    "InputError",
    "Issue",
    "RawRow",
    "RowResult",
    "__version__",
    "find_duplicates",
    "gs1_check_ok",
    "main",
    "parse_price",
    "read_rows",
    "validate_description",
    "validate_ean",
    "validate_row",
    "write_reports",
]


def main(argv=None):
    """Run the CLI. Lazy re-export so importing the package stays cheap."""
    from .cli import main as _main

    return _main(argv)
