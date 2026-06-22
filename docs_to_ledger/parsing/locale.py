"""Locale-aware parsing helpers for amounts and dates."""
from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from docs_to_ledger.model import Locale

# U+00A0 NON-BREAKING SPACE — common in French bank amount exports (unambiguous definition)
_NBSP = chr(0x00A0)


def parse_amount(value: str, locale: Locale) -> Decimal:
    """Parse a locale-formatted amount string to Decimal.

    Examples (French locale, comma decimal, space thousands):
        "1 234,56"  -> Decimal("1234.56")
        "-149,90"   -> Decimal("-149.90")
        "2500,00"   -> Decimal("2500.00")

    Thousands separators may be regular space (U+0020) or non-breaking space (U+00A0).
    """
    # Normalise non-breaking spaces (U+00A0) to regular ASCII space so one code path handles both
    cleaned = value.strip().replace(_NBSP, " ")

    if locale.thousands_separator == "space":
        # Remove all (now normalised) spaces
        cleaned = cleaned.replace(" ", "")
    elif locale.thousands_separator == "dot":
        cleaned = cleaned.replace(".", "")
    elif locale.thousands_separator == "comma":
        cleaned = cleaned.replace(",", "")
    # "none" -> no thousands separator stripping needed

    if locale.decimal_separator == "comma":
        cleaned = cleaned.replace(",", ".")
    # "dot" -> decimal separator is already a dot; nothing to do

    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse amount {value!r} with locale {locale!r}") from exc


def parse_date(value: str, locale: Locale) -> datetime.date:
    """Parse a date string using the locale's date_format.

    date_format tokens: dd=day, mm=month, yyyy=year.
    Separator is inferred from the format string (any non-alpha character between tokens).

    Raises ValueError on unparseable input.
    """
    fmt = locale.date_format  # e.g. "dd/mm/yyyy"

    # Build a strptime format string from the token-based format.
    # Replace tokens longest-first to avoid partial matches (yyyy before yy, etc.).
    strptime_fmt = fmt.replace("yyyy", "%Y").replace("mm", "%m").replace("dd", "%d")

    try:
        return datetime.datetime.strptime(value.strip(), strptime_fmt).date()
    except ValueError as exc:
        raise ValueError(
            f"Cannot parse date {value!r} with format {locale.date_format!r}: {exc}"
        ) from exc
