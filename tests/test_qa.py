"""Independent adversarial QA suite for skuv (PoC-1, tester agent).

Owner: tester. This module adds adversarial coverage on top of the
implementer suite; no implementation file is modified.

Adversarial probing found two defects here; both are fixed in the
implementation, so the tests below now run as regular passing tests:

* QA-BUG-1 (fixed) - Unicode code points that str.isdigit() accepts but int()
  rejects (superscripts such as U+00B2) reached gs1_check_ok() and raised an
  uncaught ValueError, so the CLI crashed instead of reporting EAN_FORMAT.
  EAN handling now accepts ASCII digits 0-9 only.
* QA-BUG-2 (fixed) - summary.txt "warnings" counted warning-severity issues on
  rows that were rejected (8/12/14-digit EAN with a bad checksum), although
  docs/plan.md section 5 and README say warnings counts non-13-digit EANs
  ACCEPTED with a warning; the counter now counts valid rows only.
"""

import csv
import os
import subprocess
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from skuv.cli import main
from skuv.readers import InputError, RawRow, read_rows
from skuv.validators import (
    ACCEPTED_EAN_LENGTHS,
    WARNING_EAN_LENGTH,
    find_duplicates,
    format_price,
    gs1_check_ok,
    parse_price,
    validate_description,
    validate_ean,
    validate_row,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

EAN13 = "5901234123457"
EAN13_B = "4006381333931"
EAN13_C = "9780201379624"
UPCA12 = "036000291452"
EAN8 = "96385074"
GTIN14 = "05901234123457"
EAN13_BAD = "5901234123458"


# ----------------------------------------------------------------- helpers
def codes(issues):
    return [issue.code for issue in issues]


def raw_row(lineno, ean, description, price=""):
    raw = {"ean": ean, "description": description, "price": price}
    return RawRow(lineno=lineno, ean=ean, description=description, price=price, raw=raw)


def write_text(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return path


def write_bytes(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def build_xlsx(path, rows):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["ean", "description", "price"])
    for values in rows:
        worksheet.append(list(values))
    workbook.save(path)
    return path


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def summary_of(outdir):
    return (Path(outdir) / "summary.txt").read_text(encoding="utf-8")


def run_module(args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [sys.executable, "-m", "skuv", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


# ------------------------------------------------------------ EAN validation
@pytest.mark.parametrize("value", [EAN13, EAN13_B, EAN13_C, UPCA12, EAN8, GTIN14])
def test_gs1_algorithm_accepts_known_vectors(value):
    assert gs1_check_ok(value) is True


def test_gs1_algorithm_rejects_wrong_check_digit():
    assert gs1_check_ok(EAN13_BAD) is False
    assert gs1_check_ok("1234567890123") is False


def test_ean13_wrong_checksum_is_ean_checksum():
    assert codes(validate_ean(EAN13_BAD)) == ["EAN_CHECKSUM"]


def test_ean13_all_zero_passes_checksum_by_construction():
    # Documented behaviour: the GS1 checksum of 0000000000000 is 0, which is
    # divisible by 10, so the row is accepted. The spec does not forbid it.
    assert codes(validate_ean("0" * 13)) == []
    assert validate_row(raw_row(2, "0" * 13, "Valid name", "1"), set()).is_valid is True


def test_ean_leading_and_trailing_spaces_are_trimmed():
    assert codes(validate_ean("  " + EAN13 + "  ")) == []
    assert validate_row(raw_row(2, " " + EAN13 + " ", "Valid name", "1"), set()).validated == {
        "ean": EAN13,
        "description": "Valid name",
        "price": "1",
    }


@pytest.mark.parametrize("value", [EAN8, UPCA12, GTIN14])
def test_non_13_length_eans_are_warning_only_and_stay_valid(value):
    issues = validate_ean(value)
    assert codes(issues) == [WARNING_EAN_LENGTH]
    result = validate_row(raw_row(2, value, "Valid name", "1"), set())
    assert result.is_valid is True
    assert result.error_codes == []


def test_ean8_with_bad_checksum_is_error_plus_warning():
    issues = validate_ean("12345678")
    assert codes(issues) == ["EAN_CHECKSUM", WARNING_EAN_LENGTH]
    assert validate_row(raw_row(2, "12345678", "Valid name", "1"), set()).is_valid is False


def test_gtin14_with_bad_checksum_is_error_plus_warning():
    assert set(codes(validate_ean("05901234123458"))) == {"EAN_CHECKSUM", WARNING_EAN_LENGTH}


@pytest.mark.parametrize("value", ["ABC123", "", "   ", "1234567890", "1" * 15, "590123412345X"])
def test_ean_bad_format_is_single_format_issue(value):
    assert codes(validate_ean(value)) == ["EAN_FORMAT"]


def test_ean_format_never_cascades_into_checksum():
    for value in ["abc", "1234567890", "1" * 15]:
        assert "EAN_CHECKSUM" not in codes(validate_ean(value))


def test_unicode_superscript_digits_report_ean_format_instead_of_crashing():
    assert codes(validate_ean("\u00b2" * 13)) == ["EAN_FORMAT"]


def test_cli_survives_unicode_superscript_ean(tmp_path):
    source = write_text(tmp_path, "sup.csv", "ean,description,price\n" + "\u00b2" * 13 + ",Tau vuong,1\n")
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 1
    assert (outdir / "errors.csv").is_file()


# ---------------------------------------------------------------- duplicates
def test_duplicate_flags_every_occurrence_after_the_first():
    rows = [raw_row(2, EAN13, "a", "1"), raw_row(3, EAN13, "b", "1"), raw_row(4, EAN13, "c", "1")]
    assert find_duplicates(rows) == {3, 4}


def test_duplicate_matching_uses_the_trimmed_ean():
    rows = [raw_row(2, " " + EAN13 + " ", "a", "1"), raw_row(3, EAN13, "b", "1")]
    assert find_duplicates(rows) == {3}


def test_duplicate_ignores_invalid_and_checksum_failing_eans():
    rows = [
        raw_row(2, "ABC123", "a", "1"),
        raw_row(3, "ABC123", "b", "1"),
        raw_row(4, EAN13_BAD, "c", "1"),
        raw_row(5, EAN13_BAD, "d", "1"),
    ]
    assert find_duplicates(rows) == set()


def test_duplicate_seeded_by_valid_ean_even_if_row_has_other_errors():
    rows = [raw_row(2, EAN13, "", "1"), raw_row(3, EAN13, "Clean name", "1")]
    assert find_duplicates(rows) == {3}


def test_first_occurrence_valid_second_flagged_end_to_end(tmp_path):
    source = write_text(
        tmp_path,
        "dup.csv",
        "ean,description,price\n" + EAN13 + ",Alpha,100\n" + EAN13 + ",Beta,200\n",
    )
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 1
    assert read_csv_rows(outdir / "validated.csv") == [["ean", "description", "price"], [EAN13, "Alpha", "100"]]
    assert read_csv_rows(outdir / "errors.csv") == [
        ["ean", "description", "price", "problems"],
        [EAN13, "Beta", "200", "EAN_DUP"],
    ]


def test_duplicate_detection_parity_between_csv_and_xlsx(tmp_path):
    rows = [[EAN13, "Alpha", "100"], [EAN13, "Beta", "200"], [EAN13_C, "Gamma", "300"]]
    csv_path = write_text(
        tmp_path,
        "dup.csv",
        "ean,description,price\n" + "\n".join(",".join(r) for r in rows) + "\n",
    )
    xlsx_path = build_xlsx(tmp_path / "dup.xlsx", rows)
    csv_out, xlsx_out = tmp_path / "o_csv", tmp_path / "o_xlsx"
    assert main([str(csv_path), "-o", str(csv_out)]) == 1
    assert main([str(xlsx_path), "-o", str(xlsx_out)]) == 1
    assert read_csv_rows(csv_out / "errors.csv") == read_csv_rows(xlsx_out / "errors.csv")
    assert summary_of(csv_out) == summary_of(xlsx_out)


# --------------------------------------------------------------- description
@pytest.mark.parametrize(
    "value,expected",
    [
        ("ab", ["DESC_LEN"]),
        ("abc", []),
        ("a" * 200, []),
        ("a" * 201, ["DESC_LEN"]),
        ("   ", ["DESC_EMPTY"]),
        ("\t\n ", ["DESC_EMPTY"]),
        ("", ["DESC_EMPTY"]),
    ],
)
def test_description_length_boundaries_and_blankness(value, expected):
    assert codes(validate_description(value)) == expected


@pytest.mark.parametrize("value", ["a\tb", "a\nb", "a\rb", "ab\x00cd", "ab\x1fcd", "ab\x7fcd"])
def test_description_interior_control_characters_are_flagged(value):
    assert "DESC_CTRL" in codes(validate_description(value))


def test_description_only_control_character_is_length_and_ctrl():
    assert codes(validate_description("\x01")) == ["DESC_LEN", "DESC_CTRL"]


@pytest.mark.parametrize("count,expected", [(2, ["DESC_LEN"]), (3, []), (200, []), (201, ["DESC_LEN"])])
def test_description_length_counts_astral_code_points(count, expected):
    assert codes(validate_description("\U0001f6d2" * count)) == expected


def test_description_vietnamese_diacritics_composed_and_decomposed():
    assert codes(validate_description("S\u1ee9a t\u1eafm")) == []
    decomposed = unicodedata.normalize("NFD", "S\u1ee9a t\u1eafm")
    assert codes(validate_description(decomposed)) == []


def test_description_length_is_measured_on_the_trimmed_value():
    assert codes(validate_description("  " + "a" * 200 + "  ")) == []
    assert codes(validate_description("  " + "a" * 201 + "  ")) == ["DESC_LEN"]


# --------------------------------------------------------------------- price
@pytest.mark.parametrize(
    "value,expected",
    [("", None), ("120000", Decimal("120000")), ("0", Decimal("0")), ("12000.5", Decimal("12000.5")), ("12000,5", Decimal("12000.5"))],
)
def test_price_accepts_documented_grammar(value, expected):
    parsed, issue = parse_price(value)
    assert issue is None
    assert parsed == expected


@pytest.mark.parametrize(
    "value",
    ["-1", "-0.5", "1e5", "1E5", "1,000,000", "1 000", "100VND", "$5", "5$", "+5", "12.000,5", "1.2.3", "abc", ".5", "5."],
)
def test_price_rejects_negatives_exponents_symbols_and_separators(value):
    parsed, issue = parse_price(value)
    assert parsed is None
    assert issue is not None and issue.code == "PRICE_BAD"


def test_price_comma_is_a_decimal_separator_not_a_thousands_separator():
    # Documented ambiguity: the grammar treats a lone comma as a decimal point,
    # so "10,000" normalizes to 10 rather than being rejected as thousands.
    parsed, issue = parse_price("10,000")
    assert issue is None
    assert parsed == Decimal("10")
    assert format_price(parsed) == "10"


def test_price_huge_value_survives_without_float_loss():
    huge = "9" * 40
    parsed, issue = parse_price(huge)
    assert issue is None
    assert format_price(parsed) == huge


def test_price_normalization_strips_redundant_fraction_zeros():
    assert format_price(parse_price("100.00")[0]) == "100"
    assert format_price(parse_price("0.00")[0]) == "0"
    assert format_price(parse_price("000")[0]) == "0"


def test_price_blank_and_whitespace_are_optional():
    assert parse_price("") == (None, None)
    assert parse_price("   ") == (None, None)


# ------------------------------------------------------------------ file I/O
def test_utf8_bom_csv_is_read_and_end_to_end(tmp_path):
    text = "\ufeffean,description,price\n" + EAN13 + ",Tau vuong,120000\n"
    source = write_bytes(tmp_path, "bom.csv", text.encode("utf-8"))
    rows = read_rows(source)
    assert rows[0].ean == EAN13
    assert main([str(source), "-o", str(tmp_path / "out")]) == 0


def test_semicolon_separated_csv_is_an_input_error(tmp_path):
    source = write_text(tmp_path, "semi.csv", "ean;description;price\n" + EAN13 + ";Tau;120000\n")
    with pytest.raises(InputError):
        read_rows(source)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 2


def test_empty_file_is_an_input_error(tmp_path):
    source = write_text(tmp_path, "empty.csv", "")
    with pytest.raises(InputError):
        read_rows(source)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 2


def test_header_only_file_is_valid_and_exits_zero(tmp_path):
    source = write_text(tmp_path, "header.csv", "ean,description,price\n")
    assert read_rows(source) == []
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 0
    assert summary_of(outdir) == "total: 0\nvalid: 0\ninvalid: 0\nwarnings: 0\n"


def test_missing_price_column_is_allowed(tmp_path):
    source = write_text(tmp_path, "noprice.csv", "ean,description\n" + EAN13 + ",Tau vuong\n")
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 0
    assert read_csv_rows(outdir / "validated.csv") == [["ean", "description", "price"], [EAN13, "Tau vuong", ""]]


def test_extra_unknown_columns_are_ignored(tmp_path):
    source = write_text(tmp_path, "extra.csv", "ean,description,price,Supplier,note\n" + EAN13 + ",Tau,1,ACME,zz\n")
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 0
    assert read_csv_rows(outdir / "validated.csv") == [["ean", "description", "price"], [EAN13, "Tau", "1"]]


def test_crlf_csv_matches_lf_csv(tmp_path):
    lf = write_bytes(tmp_path, "lf.csv", ("ean,description,price\n" + EAN13 + ",Tau vuong,120000\n").encode("utf-8"))
    crlf = write_bytes(tmp_path, "crlf.csv", ("ean,description,price\r\n" + EAN13 + ",Tau vuong,120000\r\n").encode("utf-8"))
    assert read_rows(crlf) == read_rows(lf)
    assert main([str(crlf), "-o", str(tmp_path / "out")]) == 0


def test_uppercase_extension_is_accepted(tmp_path):
    source = write_text(tmp_path, "LIST.CSV", "ean,description,price\n" + EAN13 + ",Tau,1\n")
    assert len(read_rows(source)) == 1
    assert main([str(source), "-o", str(tmp_path / "out")]) == 0


def test_xlsx_formula_without_cached_value_becomes_blank_price(tmp_path):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["ean", "description", "price"])
    worksheet.append([EAN13, "Tau vuong", "=1+1"])
    path = tmp_path / "formula.xlsx"
    workbook.save(path)
    rows = read_rows(path)
    assert rows[0].ean == EAN13
    assert rows[0].price == ""
    assert main([str(path), "-o", str(tmp_path / "out")]) == 0


def test_xlsx_none_cells_validate_as_empty(tmp_path):
    path = build_xlsx(tmp_path / "none.xlsx", [[EAN13, None, None]])
    outdir = tmp_path / "out"
    assert main([str(path), "-o", str(outdir)]) == 1
    assert read_csv_rows(outdir / "errors.csv")[1][3] == "DESC_EMPTY"


def test_unknown_extension_is_an_input_error(tmp_path):
    source = write_text(tmp_path, "list.xls", "ean,description\n" + EAN13 + ",Tau\n")
    with pytest.raises(InputError):
        read_rows(source)
    assert main([str(source), "-o", str(tmp_path / "out")]) == 2


# -------------------------------------------------------------- summary file
def test_summary_warnings_only_count_accepted_rows(tmp_path):
    source = write_text(tmp_path, "bad8.csv", "ean,description,price\n12345678,Sua tam,100\n")
    outdir = tmp_path / "out"
    assert main([str(source), "-o", str(outdir)]) == 1
    assert summary_of(outdir) == "total: 1\nvalid: 0\ninvalid: 1\nEAN_CHECKSUM: 1\nwarnings: 0\n"


# ---------------------------------------------------------------------- CLI
def test_exit_code_two_when_outdir_path_is_an_existing_file(tmp_path):
    source = write_text(tmp_path, "ok.csv", "ean,description,price\n" + EAN13 + ",Tau,1\n")
    blocker = write_text(tmp_path, "blocker", "x")
    assert main([str(source), "-o", str(blocker)]) == 2


def test_exit_code_two_when_input_is_a_directory(tmp_path):
    directory = tmp_path / "adir"
    directory.mkdir()
    assert main([str(directory), "-o", str(tmp_path / "out")]) == 2


def test_read_only_outdir_exits_two(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory permissions")
    source = write_text(tmp_path, "ok.csv", "ean,description,price\n" + EAN13 + ",Tau,1\n")
    outdir = tmp_path / "ro"
    outdir.mkdir()
    os.chmod(outdir, 0o555)
    try:
        assert main([str(source), "-o", str(outdir)]) == 2
    finally:
        os.chmod(outdir, 0o755)


def test_nested_missing_outdir_is_created_and_exit_codes_are_distinct(tmp_path):
    valid = write_text(tmp_path, "valid.csv", "ean,description,price\n" + EAN13 + ",Tau vuong,120000\n")
    invalid = write_text(tmp_path, "invalid.csv", "ean,description,price\n" + EAN13_BAD + ",Sua tam,99000\n")
    nested = tmp_path / "a" / "b" / "c"
    assert main([str(valid), "-o", str(nested)]) == 0
    assert (nested / "validated.csv").is_file()
    assert main([str(invalid), "-o", str(tmp_path / "o2")]) == 1
    assert main([str(tmp_path / "nope.csv"), "-o", str(tmp_path / "o3")]) == 2


def test_subprocess_exit_codes_zero_one_two(tmp_path):
    valid = write_text(tmp_path, "valid.csv", "ean,description,price\n" + EAN13 + ",Tau vuong,120000\n")
    invalid = write_text(tmp_path, "invalid.csv", "ean,description,price\n" + EAN13_BAD + ",Sua tam,99000\n")
    assert run_module([str(valid), "-o", str(tmp_path / "o1")], tmp_path).returncode == 0
    assert run_module([str(invalid), "-o", str(tmp_path / "o2")], tmp_path).returncode == 1
    assert run_module([str(tmp_path / "nope.csv"), "-o", str(tmp_path / "o3")], tmp_path).returncode == 2
    assert run_module([], tmp_path).returncode == 2


def test_subprocess_help_exits_zero():
    proc = run_module(["--help"], REPO_ROOT)
    assert proc.returncode == 0
    assert "INPUTFILE" in proc.stdout


def test_accepted_ean_lengths_constant_matches_the_spec():
    assert ACCEPTED_EAN_LENGTHS == (8, 12, 13, 14)

