"""Input readers: .csv and .xlsx SKU lists -> list[RawRow].

Design notes (docs/plan.md, section 2 and defaults A2/A6/A7):
- header names are matched case-insensitively; extra columns are ignored;
- a known column repeated in the header is an error (issue #4, R2);
- numeric spreadsheet cells are normalized to a canonical string (no trailing
  ".0", no exponent, never zero-padded);
- rows whose known fields are all blank are skipped;
- any unusable input raises InputError, which the CLI maps to exit code 2.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

REQUIRED_COLUMNS = ("ean", "description")
OPTIONAL_COLUMNS = ("price",)
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
SUPPORTED_SUFFIXES = (".csv", ".xlsx")
CSV_ENCODING = "utf-8-sig"


class InputError(Exception):
    """Raised when the input file is missing, unreadable or unsupported."""


@dataclass(frozen=True)
class RawRow:
    """One input row with the known columns mapped; values are still raw."""

    lineno: int
    ean: str
    description: str
    price: str
    raw: dict[str, str] = field(default_factory=dict)


def read_rows(path: str | Path) -> list[RawRow]:
    """Read a .csv or .xlsx SKU list and return the non-blank rows."""
    source = Path(path)
    if not source.is_file():
        raise InputError("input file not found: " + str(source))

    suffix = source.suffix.lower()
    if suffix == ".csv":
        records = _read_csv(source)
    elif suffix == ".xlsx":
        records = _read_xlsx(source)
    else:
        raise InputError(
            "unsupported input extension "
            + repr(source.suffix)
            + ": expected one of "
            + ", ".join(SUPPORTED_SUFFIXES)
        )

    rows = []
    for lineno, values in records:
        row = _build_row(lineno, values)
        if row is not None:
            rows.append(row)
    return rows


def _build_row(lineno: int, values: dict[str, str]) -> RawRow | None:
    cleaned = {name: values.get(name, "") or "" for name in KNOWN_COLUMNS}
    if not any(cleaned[name].strip() for name in KNOWN_COLUMNS):
        return None
    return RawRow(
        lineno=lineno,
        ean=cleaned["ean"],
        description=cleaned["description"],
        price=cleaned["price"],
        raw=cleaned,
    )


def _normalize_header(name: object) -> str:
    return str(name).strip().lstrip("\ufeff").lower()


def _map_header(header_names: list[object]) -> dict[str, str]:
    """Map canonical column name -> the header spelling found in the file.

    A known column (ean, description, price) that occurs more than once is
    rejected: keeping the first occurrence silently would validate a column the
    author did not mean to point at (issue #4, R2). csv and xlsx both pass
    through here, so the two formats behave identically.
    """
    found: dict[str, str] = {}
    duplicated: list[str] = []
    for name in header_names:
        if name is None:
            continue
        normalized = _normalize_header(name)
        if normalized not in KNOWN_COLUMNS:
            continue
        if normalized in found:
            duplicated.append(normalized)
        else:
            found[normalized] = str(name)
    if duplicated:
        # dict.fromkeys dedupes repeated headers while keeping their order.
        raise InputError("duplicate column(s) in header: " + ", ".join(dict.fromkeys(duplicated)))
    missing = [name for name in REQUIRED_COLUMNS if name not in found]
    if missing:
        raise InputError("missing required column(s): " + ", ".join(missing))
    return found


def _read_csv(path: Path) -> list[tuple[int, dict[str, str]]]:
    records: list[tuple[int, dict[str, str]]] = []
    try:
        with path.open("r", encoding=CSV_ENCODING, newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise InputError("input file has no header row")
            mapping = _map_header(list(reader.fieldnames))
            for row in reader:
                values = {}
                for canonical, original in mapping.items():
                    cell = row.get(original)
                    values[canonical] = "" if cell is None else str(cell)
                # csv.reader.line_num is the physical line the record ends on, so
                # a quoted value spanning several lines reports its last line
                # (issue #4, R1).
                records.append((reader.line_num, values))
    except UnicodeDecodeError as exc:
        raise InputError("cannot decode " + str(path) + " as UTF-8: " + str(exc)) from exc
    except csv.Error as exc:
        raise InputError("cannot parse csv file " + str(path) + ": " + str(exc)) from exc
    except OSError as exc:
        raise InputError("cannot read " + str(path) + ": " + str(exc)) from exc
    return records


def _read_xlsx(path: Path) -> list[tuple[int, dict[str, str]]]:
    try:
        workbook = load_workbook(filename=path, read_only=True, data_only=True)
    except (InvalidFileException, BadZipFile, OSError, KeyError, ValueError) as exc:
        raise InputError("cannot read xlsx file " + str(path) + ": " + str(exc)) from exc

    try:
        worksheet = workbook.active
        if worksheet is None:
            raise InputError("xlsx file has no active worksheet")
        rows = worksheet.iter_rows(values_only=True)
        try:
            header_cells = next(rows)
        except StopIteration:
            raise InputError("input file has no header row") from None
        header = [_cell_to_text(cell) for cell in header_cells]
        mapping = _map_header(header)
        indexes = {}
        for canonical, original in mapping.items():
            indexes[canonical] = header.index(original)

        records: list[tuple[int, dict[str, str]]] = []
        # The header is sheet row 1, so the first data row is sheet row 2
        # (issue #4, R1).
        for lineno, cells in enumerate(rows, start=2):
            values = {}
            for canonical, index in indexes.items():
                cell = cells[index] if index < len(cells) else None
                values[canonical] = _cell_to_text(cell)
            records.append((lineno, values))
    finally:
        workbook.close()
    return records


def _cell_to_text(value: object) -> str:
    """Normalize one spreadsheet cell to the canonical raw string form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, int):
        return str(value)
    return str(value).strip()
