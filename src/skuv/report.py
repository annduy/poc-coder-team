"""Report writer: validated.csv, errors.csv and summary.txt (plan section 5)."""

from __future__ import annotations

import csv
from pathlib import Path

from .validators import ERROR_CODES

VALIDATED_FILENAME = "validated.csv"
ERRORS_FILENAME = "errors.csv"
SUMMARY_FILENAME = "summary.txt"

VALIDATED_HEADER = ("ean", "description", "price")
ERRORS_HEADER = ("ean", "description", "price", "problems")

_CODE_ORDER = {code: index for index, code in enumerate(ERROR_CODES)}


def write_reports(row_results, outdir) -> None:
    """Write all three report files into outdir, creating it when missing."""
    target = Path(outdir)
    target.mkdir(parents=True, exist_ok=True)
    results = list(row_results)
    _write_validated(results, target / VALIDATED_FILENAME)
    _write_errors(results, target / ERRORS_FILENAME)
    _write_summary(results, target / SUMMARY_FILENAME)


def _write_csv(path: Path, header, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(list(header))
        writer.writerows(rows)


def _write_validated(results, path: Path) -> None:
    rows = []
    for result in results:
        if not result.is_valid:
            continue
        values = result.validated or {}
        rows.append(
            [
                values.get("ean", ""),
                values.get("description", ""),
                values.get("price", ""),
            ]
        )
    _write_csv(path, VALIDATED_HEADER, rows)


def _write_errors(results, path: Path) -> None:
    rows = []
    for result in results:
        codes = sorted(result.error_codes, key=lambda code: _CODE_ORDER.get(code, len(_CODE_ORDER)))
        if not codes:
            continue
        raw = result.raw or {}
        rows.append(
            [
                raw.get("ean", ""),
                raw.get("description", ""),
                raw.get("price", ""),
                ";".join(codes),
            ]
        )
    _write_csv(path, ERRORS_HEADER, rows)


def _write_summary(results, path: Path) -> None:
    total = len(results)
    valid = sum(1 for result in results if result.is_valid)
    invalid = total - valid

    counts = {code: 0 for code in ERROR_CODES}
    warnings = 0
    for result in results:
        for code in result.error_codes:
            counts[code] = counts.get(code, 0) + 1
        if result.is_valid:
            # plan section 5 / default A1: the warnings line counts non-13-digit
            # EANs on ACCEPTED rows only; a rejected row contributes none.
            warnings += result.warning_count

    lines = ["total: " + str(total), "valid: " + str(valid), "invalid: " + str(invalid)]
    for code in ERROR_CODES:
        if counts.get(code):
            lines.append(code + ": " + str(counts[code]))
    lines.append("warnings: " + str(warnings))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
