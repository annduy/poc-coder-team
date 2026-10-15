"""End-to-end CLI tests (spec R3/R4, docs/plan.md section 6)."""

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

from skuv.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
DATA_DIR = Path(__file__).resolve().parent / "data"

SAMPLE_CSV = DATA_DIR / "sample.csv"
SAMPLE_XLSX = DATA_DIR / "sample.xlsx"

SIMPLE_CSV = "ean,description,price\n5901234123457,Tau vuong Thom Binh,120000\n"
INVALID_CSV = "ean,description,price\n5901234123458,Sua tam,99000\n"
MISSING_COLUMN_CSV = "ean,price\n5901234123457,120000\n"

SIMPLE_SUMMARY = "total: 1\nvalid: 1\ninvalid: 0\nwarnings: 0\n"

EXPECTED_SUMMARY = (
    "total: 9\n"
    "valid: 2\n"
    "invalid: 7\n"
    "EAN_FORMAT: 1\n"
    "EAN_CHECKSUM: 1\n"
    "EAN_DUP: 1\n"
    "DESC_EMPTY: 1\n"
    "DESC_LEN: 1\n"
    "DESC_CTRL: 1\n"
    "PRICE_BAD: 1\n"
    "warnings: 1\n"
)

EXPECTED_VALIDATED = [
    ["ean", "description", "price"],
    ["5901234123457", "Tau vuong Thom Binh", "120000"],
    ["036000291452", "Dau goi", "75000"],
]

EXPECTED_PROBLEMS = [
    "EAN_CHECKSUM",
    "EAN_FORMAT",
    "EAN_DUP",
    "DESC_EMPTY",
    "DESC_LEN",
    "DESC_CTRL",
    "PRICE_BAD",
]

#: Physical source row of each errors.csv data row for the sample fixtures.
EXPECTED_ERROR_ROWS = ["3", "4", "6", "7", "8", "9", "10"]


def read_csv_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def write_csv(tmp_path: Path, text: str, name: str = "list.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def run_module(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "skuv", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


# --------------------------------------------------------------- CLI contract

def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "INPUTFILE" in capsys.readouterr().out


def test_no_args_exits_two(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_missing_input_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv"), "-o", str(tmp_path / "out")]) == 2
    assert "not found" in capsys.readouterr().err


def test_unknown_extension_exits_two(tmp_path, capsys):
    source = write_csv(tmp_path, SIMPLE_CSV, name="list.txt")
    assert main([str(source), "-o", str(tmp_path / "out")]) == 2
    assert ".csv" in capsys.readouterr().err


def test_missing_required_column_exits_two(tmp_path, capsys):
    source = write_csv(tmp_path, MISSING_COLUMN_CSV)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 2
    assert "description" in capsys.readouterr().err


def test_input_error_writes_no_reports(tmp_path):
    source = write_csv(tmp_path, MISSING_COLUMN_CSV)
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 2
    assert not outdir.exists()


def test_module_entry_point_help():
    proc = run_module(["--help"], REPO_ROOT)
    assert proc.returncode == 0
    assert "INPUTFILE" in proc.stdout


# ------------------------------------------------------------------ end-to-end

def test_all_valid_input_exits_zero(tmp_path):
    source = write_csv(tmp_path, SIMPLE_CSV)
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 0
    assert read_csv_rows(outdir / "validated.csv") == [
        ["ean", "description", "price"],
        ["5901234123457", "Tau vuong Thom Binh", "120000"],
    ]
    assert read_csv_rows(outdir / "errors.csv") == [["row", "ean", "description", "price", "problems"]]
    assert (outdir / "summary.txt").read_text(encoding="utf-8") == SIMPLE_SUMMARY


def test_any_invalid_input_exits_one(tmp_path):
    source = write_csv(tmp_path, INVALID_CSV)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 1


@pytest.mark.parametrize("fixture", [SAMPLE_CSV, SAMPLE_XLSX], ids=["csv", "xlsx"])
def test_fixture_end_to_end(fixture, tmp_path):
    outdir = tmp_path / "out"
    assert main([str(fixture), "-o", str(outdir)]) == 1

    assert read_csv_rows(outdir / "validated.csv") == EXPECTED_VALIDATED
    assert (outdir / "summary.txt").read_text(encoding="utf-8") == EXPECTED_SUMMARY

    error_rows = read_csv_rows(outdir / "errors.csv")
    assert error_rows[0] == ["row", "ean", "description", "price", "problems"]
    assert len(error_rows) == 8
    assert [row[0] for row in error_rows[1:]] == EXPECTED_ERROR_ROWS
    assert [row[4] for row in error_rows[1:]] == EXPECTED_PROBLEMS
    assert error_rows[3][2] == "duplicate row"
    assert error_rows[4][3] == "45000"
    assert error_rows[7][1] == "9780201379624"


def test_outdir_is_created_and_overwritten_silently(tmp_path):
    source = write_csv(tmp_path, SIMPLE_CSV)
    outdir = tmp_path / "nested" / "out"
    assert main([str(source), "-o", str(outdir)]) == 0
    first = (outdir / "validated.csv").read_text(encoding="utf-8-sig")
    (outdir / "summary.txt").write_text("stale", encoding="utf-8")

    assert main([str(source), "-o", str(outdir)]) == 0
    assert (outdir / "summary.txt").read_text(encoding="utf-8") == SIMPLE_SUMMARY
    assert (outdir / "validated.csv").read_text(encoding="utf-8-sig") == first


def test_default_outdir_is_out(tmp_path, monkeypatch):
    source = write_csv(tmp_path, SIMPLE_CSV)
    monkeypatch.chdir(tmp_path)
    assert main([str(source)]) == 0
    assert (tmp_path / "out" / "validated.csv").is_file()


def test_subprocess_exit_codes(tmp_path):
    valid = write_csv(tmp_path, SIMPLE_CSV, name="valid.csv")
    invalid = write_csv(tmp_path, INVALID_CSV, name="invalid.csv")
    missing = tmp_path / "nope.csv"

    assert run_module([str(valid), "-o", str(tmp_path / "o1")], tmp_path).returncode == 0
    assert run_module([str(invalid), "-o", str(tmp_path / "o2")], tmp_path).returncode == 1
    assert run_module([str(missing), "-o", str(tmp_path / "o3")], tmp_path).returncode == 2
    assert run_module([], tmp_path).returncode == 2


def test_subprocess_writes_reports(tmp_path):
    proc = run_module([str(SAMPLE_CSV), "-o", str(tmp_path / "out")], tmp_path)
    assert proc.returncode == 1, proc.stderr
    assert (tmp_path / "out" / "errors.csv").is_file()


# ------------------------------------------------ unreadable input file (S1)
def test_unreadable_input_exits_two_without_reports(tmp_path, capsys):
    if os.geteuid() == 0:
        pytest.skip("root bypasses file permissions")
    source = write_csv(tmp_path, SIMPLE_CSV)
    os.chmod(source, 0o000)
    outdir = tmp_path / "out"
    try:
        assert main([str(source), "-o", str(outdir)]) == 2
        assert "skuv: error:" in capsys.readouterr().err
        assert not outdir.exists()
    finally:
        os.chmod(source, 0o600)


def test_unreadable_input_has_no_traceback_in_subprocess(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses file permissions")
    source = write_csv(tmp_path, SIMPLE_CSV)
    os.chmod(source, 0o000)
    try:
        proc = run_module([str(source), "-o", str(tmp_path / "out")], tmp_path)
    finally:
        os.chmod(source, 0o600)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "skuv: error:" in proc.stderr


# ------------------------------------------------------- output encoding (S3)
def test_output_csv_is_utf8_sig_and_round_trips_diacritics(tmp_path):
    description = "S\u1eefa t\u1eafm d\u01b0\u1ee1ng \u1ea9m"
    source = write_csv(
        tmp_path,
        "ean,description,price\n5901234123457," + description + ",120000\n",
    )
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 0

    raw = (outdir / "validated.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert description.encode("utf-8") in raw
    assert (outdir / "errors.csv").read_bytes().startswith(b"\xef\xbb\xbf")

    with (outdir / "validated.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[1] == ["5901234123457", description, "120000"]

    assert not (outdir / "summary.txt").read_bytes().startswith(b"\xef\xbb\xbf")


# ------------------------------------------- hardening 1: source row (issue #4, R1)

DUPLICATE_HEADER_CSV = (
    "ean,description,ean,price\n"
    "5901234123457,Tau vuong Thom Binh,5901234123457,120000\n"
)


def write_xlsx(tmp_path: Path, header, rows, name: str = "list.xlsx") -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(list(header))
    for values in rows:
        worksheet.append(list(values))
    path = tmp_path / name
    workbook.save(path)
    return path


def test_errors_csv_reports_the_source_row_number(tmp_path):
    source = write_csv(
        tmp_path,
        "ean,description,price\n"
        "5901234123457,Tau vuong Thom Binh,120000\n"
        "5901234123458,Sua tam,99000\n"
        "ABC123,Sua rua mat,89000\n",
    )
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 1
    assert read_csv_rows(outdir / "errors.csv") == [
        ["row", "ean", "description", "price", "problems"],
        ["3", "5901234123458", "Sua tam", "99000", "EAN_CHECKSUM"],
        ["4", "ABC123", "Sua rua mat", "89000", "EAN_FORMAT"],
    ]


def test_errors_csv_row_is_the_physical_line_of_a_multiline_record(tmp_path):
    source = write_csv(
        tmp_path,
        "ean,description,price\n"
        '5901234123457,"Tau vuong\nThom Binh",120000\n'
        "ABC123,Sua rua mat,89000\n",
    )
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 1
    error_rows = read_csv_rows(outdir / "errors.csv")
    assert [row[0] for row in error_rows[1:]] == ["3", "4"]
    assert error_rows[1][4] == "DESC_CTRL"


def test_errors_csv_row_column_matches_between_csv_and_xlsx(tmp_path):
    rows = [
        ["5901234123457", "Tau vuong Thom Binh", "120000"],
        ["5901234123458", "Sua tam", "99000"],
        ["ABC123", "Sua rua mat", "89000"],
    ]
    csv_path = write_csv(
        tmp_path,
        "ean,description,price\n" + "\n".join(",".join(r) for r in rows) + "\n",
    )
    xlsx_path = write_xlsx(tmp_path, ["ean", "description", "price"], rows)
    csv_out, xlsx_out = tmp_path / "o_csv", tmp_path / "o_xlsx"
    assert main([str(csv_path), "-o", str(csv_out)]) == 1
    assert main([str(xlsx_path), "-o", str(xlsx_out)]) == 1
    error_rows = read_csv_rows(csv_out / "errors.csv")
    assert error_rows == read_csv_rows(xlsx_out / "errors.csv")
    assert [row[0] for row in error_rows[1:]] == ["3", "4"]


# --------------------------------------- hardening 1: duplicate header (issue #4, R2)

def test_duplicate_known_header_csv_exits_two(tmp_path, capsys):
    source = write_csv(tmp_path, DUPLICATE_HEADER_CSV)
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 2
    err = capsys.readouterr().err
    assert "skuv: error:" in err
    assert "ean" in err
    assert not outdir.exists()


def test_duplicate_known_header_message_is_identical_for_csv_and_xlsx(tmp_path, capsys):
    csv_path = write_csv(tmp_path, DUPLICATE_HEADER_CSV, name="dupe.csv")
    xlsx_path = write_xlsx(
        tmp_path,
        ["ean", "description", "ean", "price"],
        [["5901234123457", "Tau vuong Thom Binh", "5901234123457", "120000"]],
        name="dupe.xlsx",
    )
    assert main([str(csv_path), "-o", str(tmp_path / "o_csv")]) == 2
    csv_message = capsys.readouterr().err
    assert main([str(xlsx_path), "-o", str(tmp_path / "o_xlsx")]) == 2
    xlsx_message = capsys.readouterr().err
    assert csv_message == xlsx_message
    assert "ean" in csv_message
    assert not (tmp_path / "o_csv").exists()
    assert not (tmp_path / "o_xlsx").exists()


def test_duplicate_known_header_in_subprocess_exits_two(tmp_path):
    source = write_csv(tmp_path, DUPLICATE_HEADER_CSV, name="dup_sub.csv")
    proc = run_module([str(source), "-o", str(tmp_path / "out")], tmp_path)
    assert proc.returncode == 2
    assert "duplicate" in proc.stderr
    assert "ean" in proc.stderr
    assert "Traceback" not in proc.stderr
