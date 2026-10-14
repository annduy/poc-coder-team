"""Validator unit tests (spec R2, docs/plan.md section 6)."""

from decimal import Decimal

import pytest

from skuv.readers import RawRow
from skuv.validators import (
    ERROR_CODES,
    ISSUE_CODES,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    WARNING_EAN_LENGTH,
    find_duplicates,
    format_price,
    gs1_check_ok,
    parse_price,
    validate_description,
    validate_ean,
    validate_row,
)

VALID_EANS = ["5901234123457", "4006381333931", "9780201379624", "036000291452", "96385074"]
INVALID_EANS = ["5901234123458", "1234567890123", "", "abc", "5901234123456"]


def codes(issues):
    return [issue.code for issue in issues]


def make_row(lineno, ean, description, price):
    raw = {"ean": ean, "description": description, "price": price}
    return RawRow(lineno=lineno, ean=ean, description=description, price=price, raw=raw)


@pytest.mark.parametrize("value", VALID_EANS)
def test_gs1_check_ok_accepts_verified_vectors(value):
    assert gs1_check_ok(value) is True


@pytest.mark.parametrize("value", INVALID_EANS)
def test_gs1_check_ok_rejects_bad_vectors(value):
    assert gs1_check_ok(value) is False


def test_ean_non_digits_is_format_error():
    assert codes(validate_ean("ABC123")) == ["EAN_FORMAT"]


def test_ean_wrong_length_is_format_error():
    assert codes(validate_ean("1234567890")) == ["EAN_FORMAT"]


def test_ean_format_does_not_cascade_into_checksum():
    assert codes(validate_ean("12345")) == ["EAN_FORMAT"]


def test_ean_bad_checksum():
    assert codes(validate_ean("5901234123458")) == ["EAN_CHECKSUM"]


@pytest.mark.parametrize("value", ["96385074", "036000291452", "05901234123457"])
def test_ean_other_accepted_lengths_warn_but_stay_valid(value):
    issues = validate_ean(value)
    assert codes(issues) == [WARNING_EAN_LENGTH]
    assert all(issue.severity == SEVERITY_WARNING for issue in issues)


def test_duplicates_flag_every_occurrence_after_the_first():
    rows = [make_row(2, "5901234123457", "a", "1"), make_row(5, "5901234123457", "b", "1")]
    assert find_duplicates(rows) == {5}


def test_duplicates_ignore_format_invalid_eans():
    rows = [make_row(2, "ABC123", "a", "1"), make_row(3, "ABC123", "b", "1")]
    assert find_duplicates(rows) == set()


def test_duplicates_ignore_checksum_failures():
    rows = [make_row(2, "5901234123458", "a", "1"), make_row(3, "5901234123458", "b", "1")]
    assert find_duplicates(rows) == set()


def test_duplicates_match_on_the_trimmed_ean():
    rows = [make_row(2, " 5901234123457 ", "a", "1"), make_row(3, "5901234123457", "b", "1")]
    assert find_duplicates(rows) == {3}


def test_description_empty_is_desc_empty_only():
    assert codes(validate_description("")) == ["DESC_EMPTY"]


def test_description_whitespace_only_is_desc_empty_only():
    assert codes(validate_description("   ")) == ["DESC_EMPTY"]


def test_description_length_boundaries_are_inclusive():
    assert codes(validate_description("ab")) == ["DESC_LEN"]
    assert codes(validate_description("abc")) == []
    assert codes(validate_description("a" * 200)) == []
    assert codes(validate_description("a" * 201)) == ["DESC_LEN"]


@pytest.mark.parametrize("value", ["ab\x00cd", "ab\x1fcd", "ab\x7fcd"])
def test_description_control_characters_are_flagged(value):
    assert "DESC_CTRL" in codes(validate_description(value))


def test_description_length_counts_code_points():
    assert codes(validate_description("\u00e9" * 200)) == []
    assert codes(validate_description("\u00e9" * 201)) == ["DESC_LEN"]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", None),
        ("120000", Decimal("120000")),
        ("12000.5", Decimal("12000.5")),
        ("12000,5", Decimal("12000.5")),
        ("0", Decimal("0")),
    ],
)
def test_parse_price_accepts_good_values(value, expected):
    parsed, issue = parse_price(value)
    assert issue is None
    assert parsed == expected


@pytest.mark.parametrize("value", ["-1", "12.000,5", "1.2.3", "abc", "100VND", "1 000", "+5", "1e3"])
def test_parse_price_rejects_bad_values(value):
    parsed, issue = parse_price(value)
    assert parsed is None
    assert issue is not None
    assert issue.code == "PRICE_BAD"


def test_format_price_is_canonical():
    assert format_price(None) == ""
    assert format_price(Decimal("120000")) == "120000"
    assert format_price(Decimal("12000.50")) == "12000.5"


def test_validate_row_orders_issues_canonically():
    result = validate_row(make_row(2, "ABC123", "", "-5"), set())
    assert codes(result.issues) == ["EAN_FORMAT", "DESC_EMPTY", "PRICE_BAD"]
    assert result.is_valid is False
    assert result.validated is None


def test_validate_row_duplicate_only():
    result = validate_row(make_row(5, "5901234123457", "Tau vuong", "120000"), {5})
    assert codes(result.issues) == ["EAN_DUP"]
    assert result.is_valid is False
    assert result.validated is None


def test_validate_row_warning_keeps_the_row_valid_and_normalized():
    result = validate_row(make_row(5, "036000291452", "Dau goi", "75000"), set())
    assert result.is_valid is True
    assert codes(result.issues) == [WARNING_EAN_LENGTH]
    assert result.issues[0].severity == SEVERITY_WARNING
    assert result.validated == {"ean": "036000291452", "description": "Dau goi", "price": "75000"}


def test_validate_row_normalizes_trimmed_values():
    result = validate_row(make_row(2, " 5901234123457 ", "  Tau vuong  ", " 12000,5 "), set())
    assert result.is_valid is True
    assert result.validated == {"ean": "5901234123457", "description": "Tau vuong", "price": "12000.5"}


def test_error_codes_are_the_seven_canonical_codes():
    assert ISSUE_CODES == (
        "EAN_FORMAT",
        "EAN_CHECKSUM",
        "EAN_DUP",
        "DESC_EMPTY",
        "DESC_LEN",
        "DESC_CTRL",
        "PRICE_BAD",
    )
    assert ERROR_CODES == ISSUE_CODES
    assert WARNING_EAN_LENGTH not in ISSUE_CODES
    assert SEVERITY_ERROR == "error"

@pytest.mark.parametrize(
    "value",
    ["\u00b2" * 13, "\uff11" * 13, "\u0661" * 13],
    ids=["superscript", "fullwidth", "arabic-indic"],
)
def test_non_ascii_digit_eans_are_ean_format_not_a_crash(value):
    assert codes(validate_ean(value)) == ["EAN_FORMAT"]
    assert gs1_check_ok(value) is False
    result = validate_row(make_row(2, value, "Tau vuong", "1"), set())
    assert result.is_valid is False
    assert codes(result.issues) == ["EAN_FORMAT"]


def test_non_ascii_digits_are_excluded_from_duplicate_detection():
    rows = [
        make_row(2, "\uff11" * 13, "a", "1"),
        make_row(3, "\uff11" * 13, "b", "1"),
    ]
    assert find_duplicates(rows) == set()



@pytest.mark.parametrize("value", ["10,000", "1.000", "1,000", "10.000.000", "1,000,000"])
def test_probable_thousands_separator_prices_are_rejected(value):
    parsed, issue = parse_price(value)
    assert parsed is None
    assert issue is not None
    assert issue.code == "PRICE_BAD"


@pytest.mark.parametrize(
    "value,expected",
    [("12000,50", Decimal("12000.5")), ("12000.50", Decimal("12000.5")), ("10.5", Decimal("10.5"))],
)
def test_decimal_separator_prices_still_parse(value, expected):
    parsed, issue = parse_price(value)
    assert issue is None
    assert parsed == expected
    assert format_price(parsed) != ""
