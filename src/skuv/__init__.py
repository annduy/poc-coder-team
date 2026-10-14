"""skuv - SKU list validator CLI (PoC-1).

Validates SKU lists (ean, description, optional price) delivered as .csv or
.xlsx and writes cleaned output plus an error report.
"""

from .readers import InputError, RawRow, read_rows

__version__ = "0.1.0"

__all__ = ["InputError", "RawRow", "__version__", "main", "read_rows"]


def main(argv=None):
    """Run the CLI. Lazy re-export so importing the package stays cheap."""
    from .cli import main as _main

    return _main(argv)
