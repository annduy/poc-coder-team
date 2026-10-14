# Implementation Plan - PoC-1: SKU List Validator CLI (skuv)

- Spec source: issue #2 "PoC-1: SKU List Validator CLI" (repo annduy/poc-coder-team), branch feature/poc-1
- Author: planner agent, 2026-10-14
- Scope guard: implementation changes only under src/skuv/, tests/, README.md, and the CI workflow file (docs/plan.md is the planner's sole, orchestrator-approved addition)

## 1. Milestones (max 4, each with definition-of-done)

M1 - Package skeleton + CLI contract (stub pipeline)
- src/skuv/__init__.py, __main__.py, cli.py (argparse: INPUT positional, -o/--outdir default "out"); stub validators (no issues) + stub report writer; tests/conftest.py bootstrap (see A0); extend CI workflow to install pytest+openpyxl and run pytest.
- DoD: PYTHONPATH=src python -m skuv --help exits 0; no args exits 2; nonexistent input exits 2; stub run on a readable csv exits 0; CI green.

M2 - Input readers + fixtures
- readers.py: dispatch by extension; .csv via csv.DictReader (utf-8-sig, comma); .xlsx via openpyxl read_only+data_only; case-insensitive header mapping; extra columns ignored; numeric-cell normalization (A2); RawRow dataclass (lineno, ean, description, price as raw strings). Commit tests/data/sample.csv + sample.xlsx (contents in section 6).
- DoD: csv/xlsx parity test on fixtures passes; missing required column exits 2 with stderr message; header-case and extra-column tests green.

M3 - Validators (exact codes)
- validators.py per section 3 + test_validators.py full unit coverage.
- DoD: all validator unit tests green incl. verified GS1 checksum vectors; duplicate and warning behavior green; main() returns 1 on an any-invalid input at unit level.

M4 - Report writer + E2E + README + acceptance sweep
- report.py (validated.csv, errors.csv, summary.txt; mkdir -p outdir; silent overwrite); test_cli.py end-to-end on both fixtures; README "Usage" section; final check of the issue #2 acceptance list.
- DoD: full pytest suite green locally and in GitHub Actions; contents of all three output files asserted for both fixtures; silent overwrite verified by running twice.

## 2. Module layout (src/skuv - one file per concern)

- __init__.py    - version, public re-exports
- __main__.py    - from .cli import main; raise SystemExit(main())
- cli.py         - argparse, orchestration (read -> validate -> write), exit-code mapping, stderr messages
- readers.py     - read_rows(path) -> list[RawRow]; csv + xlsx readers; header mapping; InputError
- validators.py  - pure functions, issue codes, duplicate detection, row assembly; no I/O
- report.py      - write_reports(row_results, outdir); the three output files
- tests/: conftest.py (src/ path bootstrap), test_validators.py, test_readers.py, test_cli.py, data/sample.csv, data/sample.xlsx

## 3. Validator design (function level)

Severity model: Issue(code, severity) where severity is "error" or "warning". A row is invalid iff it has at least one error. The seven exact codes are error codes; warnings never invalidate a row (default A1).

Exact issue codes, canonical order:
EAN_FORMAT, EAN_CHECKSUM, EAN_DUP, DESC_EMPTY, DESC_LEN, DESC_CTRL, PRICE_BAD

- validate_ean(raw) -> list[Issue]
  - s = str(raw).strip()
  - non-digits or length not in {8, 12, 13, 14} -> EAN_FORMAT
  - length in {8, 12, 14} -> warning only (row stays valid; default A1)
  - if format ok and gs1_check_ok(s) is false -> EAN_CHECKSUM (no cascade from EAN_FORMAT)
- gs1_check_ok(digits) -> bool - single GS1 algorithm for all lengths (8/12/13/14): from the rightmost data digit, weights alternate 3,1,3,1...; (weighted_sum + check_digit) mod 10 == 0. Verified vectors for tests: 5901234123457 ok, 4006381333931 ok, 9780201379624 ok, 036000291452 ok (UPC-A, 12), 96385074 ok (EAN-8), 5901234123458 fails.
- find_duplicates(rows) -> set of linenos - group by trimmed ean among rows whose ean passed format+checksum; every occurrence after the first gets EAN_DUP (default A3).
- validate_description(raw) -> list[Issue]
  - t = raw.strip(); empty -> DESC_EMPTY (only; no cascade)
  - not (3 <= code-point-length(t) <= 200) -> DESC_LEN (boundaries inclusive, default A8)
  - any char with unicodedata.category == "Cc" (U+0000..U+001F, U+007F) -> DESC_CTRL
- parse_price(raw) -> (Decimal | None, Issue | None)
  - empty after strip -> OK (price optional)
  - matches ^[0-9]+([.,][0-9]+)?$ -> Decimal, normalizing "," decimal separator to "." ; anything else -> PRICE_BAD (negatives, currency symbols, thousands separators all fail) (default A4). Use Decimal, never float.
- validate_row(row, dup linenos) -> RowResult{issues in canonical order, is_valid, normalized (ean, description, price) for valid rows}

## 4. CLI structure

    python -m skuv INPUTFILE [-o OUTDIR]        (OUTDIR default: ./out, created if missing)

- argparse: positional input (file path), -o/--outdir; argparse's own usage errors already exit 2.
- exit 0: file processed, zero invalid rows.
- exit 1: at least one invalid row (reports still written).
- exit 2: usage error; missing/unreadable file; unknown extension; missing required ean or description column (default A5). Message to stderr; no reports written.
- Import bootstrap: PYTHONPATH=src (see A0).

## 5. Outputs (report.py)

- validated.csv - header ean,description,price; only rows with zero error issues; normalized: ean trimmed as string, description trimmed, price canonical decimal with "." separator (empty when absent).
- errors.csv - original header plus trailing problems column; original raw values; problems = ";"-joined codes in canonical order, e.g. EAN_CHECKSUM;DESC_EMPTY. Only rows with at least one error issue.
- summary.txt - lines: total / valid / invalid; then per-code error counts (only >0, canonical order); then "warnings: N" for accepted non-13-length EANs.
- outdir = mkdir(parents=True, exist_ok=True); existing files overwritten silently.

## 6. Test plan (pytest), mapped to spec

Fixture files tests/data/sample.csv and tests/data/sample.xlsx share the same 9 rows (xlsx stores row 1 ean as a numeric cell to exercise A2; row 4 ean must be a text cell to keep its leading zero):

| # | ean           | description            | price  | expected            |
|---|---------------|------------------------|--------|---------------------|
| 1 | 5901234123457 | Tau vuong Thom Binh    | 120000 | valid               |
| 2 | 5901234123458 | Sua tam                | 99000  | EAN_CHECKSUM        |
| 3 | ABC123        | Sua rua mat            | 89000  | EAN_FORMAT          |
| 4 | 036000291452  | Dau goi                | 75000  | valid + warning     |
| 5 | 5901234123457 | duplicate row          | 120000 | EAN_DUP             |
| 6 | 4006381333931 | (blank)                | 45000  | DESC_EMPTY          |
| 7 | 2001234567893 | 201-char description   | 45000  | DESC_LEN            |
| 8 | 4901234567894 | contains U+0001        | 0      | DESC_CTRL           |
| 9 | 9780201379624 | Tay trang              | -5     | PRICE_BAD           |

Expected fixture totals: total 9, valid 2, invalid 7, warnings 1, each error code exactly once.

- test_validators.py -> spec R2: checksum valid/invalid vectors (above); format (non-digits, length 10 -> EAN_FORMAT; lengths 8/12/14 -> warning-only); duplicates (first clean, later flagged; format-invalid eans excluded); description boundaries (2, 3, 200, 201 code points; whitespace-only -> DESC_EMPTY; U+0000/U+001F/U+007F -> DESC_CTRL); price ok ("", "120000", "12000.5", "12000,5") and bad ("-1", "12.000,5", "1.2.3", "abc", "100VND").
- test_readers.py -> spec R1: header case-insensitivity; extra columns ignored; csv/xlsx parity on fixtures; numeric ean cell normalization; missing required column raises InputError.
- test_cli.py -> spec R3/R4 e2e (invoke main(argv) directly, plus one subprocess test for exit codes): exit 0 all-valid input; exit 1 any-invalid; exit 2 for missing file / unknown extension / missing column / no args; --help exits 0; three output files with expected contents; problems ";"-joined; silent overwrite by running twice.

## 7. Dependencies

- Python 3.12 stdlib only: argparse, csv, dataclasses, decimal, pathlib, re, unicodedata.
- Xlsx library: openpyxl - justification: reads .xlsx cell values directly with a tiny dependency footprint, while pandas would pull numpy just to iterate a worksheet we walk cell-by-cell anyway.

## 8. Risks / spec ambiguities -> chosen defaults

- A0 "python -m skuv" import path vs acceptance rule "no changes outside src/skuv, tests, README.md, workflow file": default = NO pyproject.toml; tests/conftest.py inserts src/ into sys.path; README and CI invoke with PYTHONPATH=src. Alternative (needs sign-off, adds a root file): minimal pyproject.toml + pip install -e .
- A1 Spec says accept 8 or 12-14 length "with warning", but the fixed code list has no warning code: default = such rows remain VALID (validated.csv, exit code unaffected); warning surfaced only as a count in summary.txt, not in errors.csv; Issue carries severity so flipping to a warning code later is trivial.
- A2 xlsx numeric ean cells lose leading zeros / render in exponent form: default = normalize numeric cells to canonical integer string (no trailing .0, no exponent); never zero-pad; a 12-digit result simply falls into the warning bucket.
- A3 Duplicates: exact match on trimmed ean; first occurrence clean, later ones EAN_DUP; only eans that passed format+checksum participate.
- A4 Price grammar: ^[0-9]+([.,][0-9]+)?$ only (dot or comma decimal, no thousands separators, no signs/symbols); Decimal internally; "." canonical in output.
- A5 Missing required columns, unparseable file, or unknown extension -> exit 2 (input error) with stderr message; optional price column missing is fine.
- A6 CSV dialect: UTF-8 (BOM tolerated via utf-8-sig), comma delimiter, header row required.
- A7 Ragged rows: missing per-row values become empty strings and validate normally (ean "" -> EAN_FORMAT, description "" -> DESC_EMPTY); rows where all three fields are blank are skipped.
- A8 DESC_LEN measured in Unicode code points on the trimmed value; 3 and 200 inclusive.
- A9 DESC_CTRL = Unicode category Cc. An all-blank description yields DESC_EMPTY only (no DESC_LEN/DESC_CTRL cascade).
- A10 Outdir default ./out relative to CWD; created if missing; silent overwrite.
- A11 CI runner needs pip install pytest openpyxl before running pytest (networked GitHub Actions runner).

Out of scope per spec (do NOT build): database, web UI, API server, scheduling, i18n.
