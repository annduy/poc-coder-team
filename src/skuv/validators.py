"""Pure validation logic for SKU rows - no I/O.

Severity model (docs/plan.md, section 3): an issue is either an "error" or a
"warning" and a row is invalid iff it carries at least one error. The seven
ISSUE_CODES are all error codes; an EAN whose length is 8, 12 or 14 adds a
warning only (default A1), so the row stays valid and the warning is merely
counted in summary.txt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

#: Canonical order of the seven error codes (docs/plan.md, section 3).
ISSUE_CODES = (
    "EAN_FORMAT",
    "EAN_CHECKSUM",
    "EAN_DUP",
    "DESC_EMPTY",
    "DESC_LEN",
    "DESC_CTRL",
    "PRICE_BAD",
)
ERROR_CODES = ISSUE_CODES

#: Warning code - deliberately outside ISSUE_CODES so it never reaches errors.csv.
WARNING_EAN_LENGTH = "EAN_LENGTH"

ACCEPTED_EAN_LENGTHS = (8, 12, 13, 14)
WARNED_EAN_LENGTHS = (8, 12, 14)

DESC_MIN_LENGTH = 3
DESC_MAX_LENGTH = 200

PRICE_PATTERN = re.compile(r"^[0-9]+([.,][0-9]+)?$")


@dataclass(frozen=True)
class Issue:
    """One problem found on a row."""

    code: str
    severity: str = SEVERITY_ERROR
    message: str = ""


@dataclass
class RowResult:
    """Validation outcome for a single input row."""

    lineno: int
    raw: dict[str, str] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    validated: dict[str, str] | None = None

    @property
    def is_valid(self) -> bool:
        """True when the row carries no error-severity issue."""
        return not any(issue.severity == SEVERITY_ERROR for issue in self.issues)

    @property
    def error_codes(self) -> list[str]:
        return [issue.code for issue in self.issues if issue.severity == SEVERITY_ERROR]

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == SEVERITY_WARNING)


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _issue_sort_key(issue: Issue) -> tuple[int, int]:
    try:
        index = ISSUE_CODES.index(issue.code)
    except ValueError:
        index = len(ISSUE_CODES)
    rank = 0 if issue.severity == SEVERITY_ERROR else 1
    return (index, rank)


def gs1_check_ok(digits: str) -> bool:
    """One GS1 check-digit algorithm for 8/12/13/14 digit codes.

    Walking left from the rightmost data digit the weights alternate 3,1,3,1...;
    the weighted data sum plus the check digit must be divisible by 10.
    """
    if not digits or not digits.isdigit():
        return False
    weighted = 0
    for offset, char in enumerate(reversed(digits[:-1])):
        weighted += int(char) * (3 if offset % 2 == 0 else 1)
    return (weighted + int(digits[-1])) % 10 == 0


def validate_ean(raw: object) -> list[Issue]:
    """Return the EAN issues for one raw cell value."""
    value = _text(raw).strip()
    if not value.isdigit() or len(value) not in ACCEPTED_EAN_LENGTHS:
        return [
            Issue(
                "EAN_FORMAT",
                SEVERITY_ERROR,
                "ean must be 8, 12, 13 or 14 digits, got " + repr(value),
            )
        ]

    issues: list[Issue] = []
    if not gs1_check_ok(value):
        issues.append(Issue("EAN_CHECKSUM", SEVERITY_ERROR, "ean fails the GS1 check digit: " + value))
    if len(value) in WARNED_EAN_LENGTHS:
        issues.append(
            Issue(
                WARNING_EAN_LENGTH,
                SEVERITY_WARNING,
                "ean length " + str(len(value)) + " accepted with warning",
            )
        )
    return issues


def find_duplicates(rows) -> set[int]:
    """Line numbers of rows repeating an earlier valid EAN (default A3)."""
    seen: set[str] = set()
    duplicates: set[int] = set()
    for row in rows:
        ean = _text(getattr(row, "ean", "")).strip()
        if not ean.isdigit() or len(ean) not in ACCEPTED_EAN_LENGTHS or not gs1_check_ok(ean):
            continue
        if ean in seen:
            duplicates.add(getattr(row, "lineno", None))
        else:
            seen.add(ean)
    duplicates.discard(None)
    return duplicates


def validate_description(raw: object) -> list[Issue]:
    """Return the description issues for one raw cell value."""
    value = _text(raw).strip()
    if not value:
        return [Issue("DESC_EMPTY", SEVERITY_ERROR, "description is empty after trimming")]

    issues: list[Issue] = []
    if not DESC_MIN_LENGTH <= len(value) <= DESC_MAX_LENGTH:
        issues.append(
            Issue(
                "DESC_LEN",
                SEVERITY_ERROR,
                "description must be 3..200 characters, got " + str(len(value)),
            )
        )
    if any(unicodedata.category(char) == "Cc" for char in value):
        issues.append(Issue("DESC_CTRL", SEVERITY_ERROR, "description contains control characters"))
    return issues


def parse_price(raw: object) -> tuple[Decimal | None, Issue | None]:
    """Parse an optional price. Returns (value, issue); both empty when blank."""
    value = _text(raw).strip()
    if not value:
        return None, None
    if not PRICE_PATTERN.match(value):
        return None, Issue("PRICE_BAD", SEVERITY_ERROR, "price must be a non-negative number: " + repr(value))
    try:
        return Decimal(value.replace(",", ".")), None
    except InvalidOperation:  # pragma: no cover - guarded by PRICE_PATTERN
        return None, Issue("PRICE_BAD", SEVERITY_ERROR, "price is not a valid decimal: " + repr(value))


def format_price(value: Decimal | None) -> str:
    """Canonical decimal text with a "." separator (empty for a missing price)."""
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def validate_row(row, duplicates: set[int] | None = None) -> RowResult:
    """Validate one input row; issue order follows the canonical code order."""
    duplicates = duplicates or set()
    lineno = getattr(row, "lineno", 0)
    ean = _text(getattr(row, "ean", ""))
    description = _text(getattr(row, "description", ""))
    price = _text(getattr(row, "price", ""))
    raw = dict(getattr(row, "raw", None) or {"ean": ean, "description": description, "price": price})

    issues: list[Issue] = []
    issues.extend(validate_ean(ean))
    if lineno in duplicates:
        issues.append(Issue("EAN_DUP", SEVERITY_ERROR, "ean repeats an earlier row: " + ean.strip()))
    issues.extend(validate_description(description))
    price_value, price_issue = parse_price(price)
    if price_issue is not None:
        issues.append(price_issue)
    issues.sort(key=_issue_sort_key)

    result = RowResult(lineno=lineno, raw=raw, issues=issues)
    if result.is_valid:
        result.validated = {
            "ean": ean.strip(),
            "description": description.strip(),
            "price": format_price(price_value),
        }
    return result
