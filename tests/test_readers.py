"""Reader tests: header mapping, normalization, csv/xlsx parity (spec R1)."""

import os
from pathlib import Path

import pytest
from openpyxl import Workbook

from skuv.readers import InputError, read_rows

DATA_DIR = Path(__file__).resolve().parent / "data"
SAMPLE_CSV = DATA_DIR / "sample.csv"
SAMPLE_XLSX = DATA_DIR / "sample.xlsx"


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_header_case_insensitive_and_extra_columns_ignored(tmp_path):
    path = write(
        tmp_path / "case.csv",
        "EAN,Description,Price,Supplier\n5901234123457,Tau vuong,120000,ACME\n",
    )
    rows = read_rows(path)
    assert len(rows) == 1
    assert rows[0].ean == "5901234123457"
    assert rows[0].description == "Tau vuong"
    assert rows[0].price == "120000"
    assert sorted(rows[0].raw) == ["description", "ean", "price"]


def test_optional_price_column_may_be_absent(tmp_path):
    path = write(tmp_path / "noprice.csv", "ean,description\n5901234123457,Tau vuong\n")
    rows = read_rows(path)
    assert rows[0].price == ""


def test_missing_required_column_raises_input_error(tmp_path):
    path = write(tmp_path / "bad.csv", "ean,price\n5901234123457,120000\n")
    with pytest.raises(InputError) as excinfo:
        read_rows(path)
    assert "description" in str(excinfo.value)


def test_missing_file_raises_input_error(tmp_path):
    with pytest.raises(InputError):
        read_rows(tmp_path / "nope.csv")


def test_unknown_extension_raises_input_error(tmp_path):
    path = write(tmp_path / "list.txt", "ean,description\n5901234123457,x\n")
    with pytest.raises(InputError):
        read_rows(path)


def test_csv_xlsx_parity_on_fixtures():
    assert read_rows(SAMPLE_CSV) == read_rows(SAMPLE_XLSX)


def test_fixture_rows_and_line_numbers():
    rows = read_rows(SAMPLE_CSV)
    assert [row.lineno for row in rows] == [2, 3, 4, 5, 6, 7, 8, 9, 10]


def test_numeric_xlsx_ean_cell_is_normalized(tmp_path):
    path = tmp_path / "numeric.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["ean", "description", "price"])
    worksheet.append([5901234123457, "Tau vuong", 120000])
    workbook.save(path)
    rows = read_rows(path)
    assert rows[0].ean == "5901234123457"
    assert rows[0].price == "120000"


def test_utf8_bom_is_tolerated(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("\ufeffean,description,price\n5901234123457,Tau vuong,1\n".encode("utf-8"))
    rows = read_rows(path)
    assert rows[0].description == "Tau vuong"


def test_blank_rows_are_skipped(tmp_path):
    path = write(tmp_path / "blank.csv", "ean,description,price\n,,\n5901234123457,x,1\n")
    rows = read_rows(path)
    assert len(rows) == 1
    assert rows[0].lineno == 3


def test_ragged_row_becomes_empty_values(tmp_path):
    path = write(tmp_path / "ragged.csv", "ean,description,price\n5901234123457\n")
    rows = read_rows(path)
    assert rows[0].description == ""
    assert rows[0].price == ""


def test_control_character_is_preserved_in_fixture():
    rows = read_rows(SAMPLE_CSV)
    assert "\x7f" in rows[7].description


def test_unreadable_file_raises_input_error(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses file permissions")
    path = write(tmp_path / "secret.csv", "ean,description\n5901234123457,Tau vuong\n")
    os.chmod(path, 0o000)
    try:
        with pytest.raises(InputError) as excinfo:
            read_rows(path)
        assert "cannot read" in str(excinfo.value)
    finally:
        os.chmod(path, 0o600)
