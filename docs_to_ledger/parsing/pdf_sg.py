"""SG (Société Générale) PDF statement parser using pdfplumber word extraction.

Each page has transaction rows where each row starts with an operation date
(DD/MM/YYYY at ~x=31) followed by a value date, description words, and a
single amount that lands in either the Débit or Crédit column.  Multi-line
descriptions follow at x≈124 until the next transaction or page boundary.

Column boundaries are derived from the Débit/Crédit header words found on
each page, so the parser adapts if the layout shifts across pages.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from docs_to_ledger import fingerprint
from docs_to_ledger.model import SourceRule, Transaction
from docs_to_ledger.parsing.locale import parse_amount, parse_date

from . import ParseFailure, ParseResult

_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_AMOUNT_RE = re.compile(r"^\d[\d.]*,\d{2}\*?$")

_LINE_Y_TOLERANCE = 3.0
_DESC_X_MIN = 80.0
_DESC_X_MAX = 250.0
_AMOUNT_X_MIN = 400.0


def _group_words_by_line(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [sorted_words[0]]
    current_y: float = sorted_words[0]["top"]
    for word in sorted_words[1:]:
        if abs(word["top"] - current_y) <= _LINE_Y_TOLERANCE:
            current.append(word)
        else:
            lines.append(sorted(current, key=lambda w: w["x0"]))
            current = [word]
            current_y = word["top"]
    lines.append(sorted(current, key=lambda w: w["x0"]))
    return lines


def _ascii_alpha(text: str) -> str:
    """Lowercase, strip accents, keep only ASCII a-z."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if c.isascii() and c.isalpha())


def _find_debit_credit_boundary(words: list[dict[str, Any]]) -> float | None:
    """Return x midpoint between the Débit and Crédit column headers."""
    debit_x1: float | None = None
    credit_x0: float | None = None
    for w in words:
        a = _ascii_alpha(w["text"])
        if a == "debit" and debit_x1 is None:
            debit_x1 = w["x1"]
        elif a == "credit" and credit_x0 is None:
            credit_x0 = w["x0"]
    if debit_x1 is not None and credit_x0 is not None:
        return (debit_x1 + credit_x0) / 2.0
    return None


def _find_amount(line_words: list[dict[str, Any]]) -> tuple[int, bool] | tuple[None, None]:
    """Return (word_index, is_amount_like) for the rightmost amount in a line.

    Only words at x0 > _AMOUNT_X_MIN are considered to avoid false matches on
    reference numbers inside descriptions.
    """
    for i in range(len(line_words) - 1, -1, -1):
        w = line_words[i]
        if w["x0"] >= _AMOUNT_X_MIN and _AMOUNT_RE.match(w["text"]):
            return i, True
    return None, None


def _flush(
    pending: dict[str, Any],
    source: SourceRule,
    counter: dict[str, int],
    file_str: str,
    failures: list[ParseFailure],
) -> Transaction | None:
    try:
        txn_date = parse_date(pending["date_str"], source.locale)
    except ValueError as exc:
        failures.append(
            ParseFailure(file=file_str, line=pending["line"], reason=str(exc))
        )
        return None

    raw_amount = pending["amount_str"]
    if raw_amount is None:
        failures.append(
            ParseFailure(
                file=file_str,
                line=pending["line"],
                reason="No amount found for transaction",
            )
        )
        return None

    raw_amount = raw_amount.rstrip("*")
    try:
        amount = abs(parse_amount(raw_amount, source.locale))
    except ValueError as exc:
        failures.append(
            ParseFailure(file=file_str, line=pending["line"], reason=str(exc))
        )
        return None

    is_debit: bool = pending["is_debit"]
    debit = amount if is_debit else None
    credit = None if is_debit else amount

    description = " ".join(pending["desc_parts"])
    normalized = fingerprint.normalize_description(description)
    txn_id = fingerprint.transaction_id(source.account, txn_date, amount, normalized)
    occ = counter.get(txn_id, 0)
    counter[txn_id] = occ + 1

    return Transaction(
        date=txn_date,
        description=description,
        debit=debit,
        credit=credit,
        account=source.account,
        source_file=file_str,
        txn_id=txn_id,
        occurrence=occ,
    )


def parse_pdf_sg(file_path: Path, source: SourceRule) -> ParseResult:
    """Parse an SG-layout PDF statement using pdfplumber word-position extraction."""
    transactions: list[Transaction] = []
    failures: list[ParseFailure] = []
    counter: dict[str, int] = {}
    file_str = str(file_path)
    global_line = 0

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue

            boundary = _find_debit_credit_boundary(words)
            if boundary is None:
                continue

            pending: dict[str, Any] | None = None

            for line_words in _group_words_by_line(words):
                global_line += 1
                if not line_words:
                    continue

                first = line_words[0]

                if _DATE_RE.match(first["text"]):
                    if pending is not None:
                        txn = _flush(pending, source, counter, file_str, failures)
                        if txn is not None:
                            transactions.append(txn)

                    amt_idx, _ = _find_amount(line_words)
                    if amt_idx is not None:
                        amt_word = line_words[amt_idx]
                        is_debit = amt_word["x0"] < boundary
                        amount_str: str | None = amt_word["text"]
                        desc_words = [
                            w["text"]
                            for i, w in enumerate(line_words[2:], start=2)
                            if i != amt_idx
                        ]
                    else:
                        is_debit = True
                        amount_str = None
                        desc_words = [w["text"] for w in line_words[2:]]

                    pending = {
                        "date_str": first["text"],
                        "desc_parts": desc_words,
                        "amount_str": amount_str,
                        "is_debit": is_debit,
                        "line": global_line,
                    }

                elif pending is not None and _DESC_X_MIN < first["x0"] < _DESC_X_MAX:
                    pending["desc_parts"].extend(w["text"] for w in line_words)

            if pending is not None:
                txn = _flush(pending, source, counter, file_str, failures)
                if txn is not None:
                    transactions.append(txn)

    return ParseResult(transactions=transactions, failures=failures)
