# poc-coder-team

PoC repository for the OpenClaw multi-agent coder team (planner / implementer /
tester / reviewer). The PoC-1 deliverable is the `skuv` SKU list validator in
`src/skuv/`.

## skuv - SKU list validator

Validates SKU lists (barcode | description | optional price) delivered as `.csv`
or `.xlsx` and writes a cleaned list plus an error report.

### Usage

```console
$ PYTHONPATH=src python3 -m skuv tests/data/sample.csv -o out
$ PYTHONPATH=src python3 -m skuv tests/data/sample.xlsx -o out
$ PYTHONPATH=src python3 -m skuv --help
```

Arguments:

- `INPUTFILE` - the `.csv` or `.xlsx` list to validate (required).
- `-o/--outdir` - output directory, created if missing (default: `out`).

Exit codes:

- `0` - file processed, no invalid rows.
- `1` - file processed, at least one invalid row (reports are still written).
- `2` - usage error, missing or unreadable input, unsupported extension, or a
  missing required column; the reason goes to stderr and no reports are written.

### Input format

Headers are matched case-insensitively and extra columns are ignored. `ean` and
`description` are required; `price` is optional. Rows whose three known fields
are all blank are skipped. A UTF-8 byte-order mark is tolerated in CSV files.

Prices use `.` or `,` as the decimal separator; a separator followed by exactly
three digits (e.g. `10,000` or `1.000`) is rejected as a probable thousands
separator (`PRICE_BAD`).

### Outputs (out/)

- `validated.csv` - `ean,description,price` for every row without an error, with
  normalized values (trimmed text, canonical decimal price using `.`).
- `errors.csv` - `ean,description,price,problems` with the raw row values and the
  `;`-joined issue codes in canonical order, e.g. `EAN_CHECKSUM;DESC_EMPTY`.
- `summary.txt` - `total`, `valid`, `invalid`, the per-code error counts, and the
  number of non-13-digit EANs accepted with a warning.

Existing files are overwritten silently on every run. `validated.csv` and
`errors.csv` are written as UTF-8 with a BOM (`utf-8-sig`, Excel-friendly);
`summary.txt` is plain UTF-8.

### Issue codes

`EAN_FORMAT`, `EAN_CHECKSUM`, `EAN_DUP`, `DESC_EMPTY`, `DESC_LEN`,
`DESC_CTRL`, `PRICE_BAD`. All seven are error codes. An EAN of length 8, 12 or 14
is accepted with a warning only - the row stays valid and is counted in
`summary.txt`.

### Tests

```console
$ python3 -m pip install pytest openpyxl
$ python3 -m pytest tests/ -q
```

`tests/data/sample.csv` and `tests/data/sample.xlsx` hold the same nine rows and
cover every issue code once, plus the non-13-digit EAN warning.
