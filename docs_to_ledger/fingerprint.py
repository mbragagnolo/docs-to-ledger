from __future__ import annotations

import datetime
import hashlib
import re
import unicodedata
from decimal import Decimal


def normalize_description(s: str) -> str:
    """Lowercase, strip accents-normalise, remove punctuation, collapse whitespace."""
    s = s.lower()
    s = unicodedata.normalize("NFC", s)
    # Replace any character that is not a letter, digit, or whitespace with a space.
    s = re.sub(r"[^\w\s]", " ", s)
    # Collapse runs of whitespace (including non-breaking spaces) to a single space.
    s = re.sub(r"\s+", " ", s).strip()
    return s


def transaction_id(
    account: str,
    date: datetime.date,
    amount: Decimal,
    normalized_description: str,
) -> str:
    """Stable SHA-256 fingerprint over the four identifying dimensions of a transaction.

    The occurrence index is NOT included here; callers track it separately so that
    legitimately identical rows (same date/amount/description on one statement) each
    get a distinct (txn_id, occurrence) pair without changing the base id.
    """
    raw = f"{account}|{date.isoformat()}|{amount}|{normalized_description}"
    return hashlib.sha256(raw.encode()).hexdigest()
