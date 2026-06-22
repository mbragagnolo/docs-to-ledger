import datetime
from decimal import Decimal

from docs_to_ledger.fingerprint import normalize_description, transaction_id

_DATE = datetime.date(2026, 6, 15)
_ACCOUNT = "SG Compte Courant"
_AMOUNT = Decimal("149.90")
_DESC = "carte super u"


def test_deterministic() -> None:
    assert transaction_id(_ACCOUNT, _DATE, _AMOUNT, _DESC) == transaction_id(
        _ACCOUNT, _DATE, _AMOUNT, _DESC
    )


def test_different_account() -> None:
    assert transaction_id(_ACCOUNT, _DATE, _AMOUNT, _DESC) != transaction_id(
        "OTHER", _DATE, _AMOUNT, _DESC
    )


def test_different_date() -> None:
    assert transaction_id(_ACCOUNT, _DATE, _AMOUNT, _DESC) != transaction_id(
        _ACCOUNT, datetime.date(2026, 6, 16), _AMOUNT, _DESC
    )


def test_different_amount() -> None:
    assert transaction_id(_ACCOUNT, _DATE, _AMOUNT, _DESC) != transaction_id(
        _ACCOUNT, _DATE, Decimal("150.00"), _DESC
    )


def test_different_description() -> None:
    assert transaction_id(_ACCOUNT, _DATE, _AMOUNT, _DESC) != transaction_id(
        _ACCOUNT, _DATE, _AMOUNT, "virement"
    )


def test_normalize_case() -> None:
    assert normalize_description("CARTE SUPER U") == normalize_description("carte super u")


def test_normalize_whitespace() -> None:
    assert normalize_description("CARTE  SUPER   U") == normalize_description("CARTE SUPER U")


def test_normalize_leading_trailing() -> None:
    assert normalize_description("  CARTE SUPER U  ") == normalize_description("CARTE SUPER U")


def test_normalize_punctuation_removed() -> None:
    result = normalize_description("CARTE, SUPER-U!")
    assert "," not in result
    assert "-" not in result
    assert "!" not in result


def test_normalize_punctuation_becomes_word_boundary() -> None:
    # Punctuation replaced by space, then collapsed — words survive.
    result = normalize_description("SUPER-U")
    assert "super" in result
    assert "u" in result
