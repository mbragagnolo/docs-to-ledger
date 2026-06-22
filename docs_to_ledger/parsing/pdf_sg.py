"""SG (Société Générale) PDF statement parser using pdfplumber.

PROVISIONAL: Built against a documented assumed SG layout.
A real SG PDF sample is needed to verify this profile.

Expected SG PDF layout (assumption):
- Table rows with columns: Date, Description, Debit, Credit
- Same French locale as CSV (dd/mm/yyyy, comma decimal)
- Uses pdfplumber's extract_table() on each page
- Same failure semantics as CSV parser
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pdfplumber

from docs_to_ledger import fingerprint
from docs_to_ledger.model import SourceRule, Transaction
from docs_to_ledger.parsing.locale import parse_amount, parse_date

from . import ParseFailure, ParseResult

# Assumed column names in the SG PDF table.  The parser falls back to positional
# matching when the header row cannot be identified.
_SG_EXPECTED_HEADERS = ("date", "description", "debit", "credit")


def _cell_value(row: list[Any], idx: int | None) -> str:
    """Extract a stripped string cell from *row* at *idx*, returning '' for None/missing."""
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _find_col(headers: list[str], name: str) -> int | None:
    """Return position of *name* in *headers*, or None if absent."""
    try:
        return headers.index(name)
    except ValueError:
        return None


def parse_pdf_sg(file_path: Path, source: SourceRule) -> ParseResult:
    """Parse an SG-layout PDF statement using pdfplumber.

    Returns an empty ParseResult (no transactions, no failures) when the PDF
    contains no extractable tables — this covers minimal/blank PDFs used in
    tests and gracefully handles pages without tabular content.
    """
    transactions: list[Transaction] = []
    failures: list[ParseFailure] = []
    occurrence_counter: dict[str, int] = {}

    col_map = source.column_map  # may be empty for pdf profile
    date_col_name = col_map.get("date", "date").lower()
    desc_col_name = col_map.get("description", "description").lower()
    debit_col_name = col_map.get("debit", "debit").lower()
    credit_col_name = col_map.get("credit", "credit").lower()

    global_row_index = 0  # running count across all pages (for failure line numbers)

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            # First row is assumed to be headers
            headers = [str(h).strip().lower() if h else "" for h in table[0]]

            date_idx = _find_col(headers, date_col_name)
            desc_idx = _find_col(headers, desc_col_name)
            debit_idx = _find_col(headers, debit_col_name)
            credit_idx = _find_col(headers, credit_col_name)

            # Fall back to positional indices when no header match found
            if date_idx is None and desc_idx is None:
                if len(headers) >= 4:
                    date_idx, desc_idx, debit_idx, credit_idx = 0, 1, 2, 3
                else:
                    continue  # cannot parse this page

            for raw_row in table[1:]:
                global_row_index += 1
                line_number = global_row_index

                raw_date = _cell_value(raw_row, date_idx)
                if not raw_date:
                    continue  # skip empty rows (common in PDF tables)

                try:
                    txn_date = parse_date(raw_date, source.locale)
                except ValueError as exc:
                    failures.append(
                        ParseFailure(
                            file=str(file_path),
                            line=line_number,
                            reason=f"Unparseable date {raw_date!r}: {exc}",
                        )
                    )
                    continue

                raw_debit = _cell_value(raw_row, debit_idx)
                raw_credit = _cell_value(raw_row, credit_idx)

                debit: Decimal | None = None
                credit: Decimal | None = None

                if raw_debit:
                    try:
                        debit = abs(parse_amount(raw_debit, source.locale))
                    except ValueError as exc:
                        failures.append(
                            ParseFailure(
                                file=str(file_path),
                                line=line_number,
                                reason=f"Unparseable debit {raw_debit!r}: {exc}",
                            )
                        )
                        continue

                if raw_credit:
                    try:
                        credit = abs(parse_amount(raw_credit, source.locale))
                    except ValueError as exc:
                        failures.append(
                            ParseFailure(
                                file=str(file_path),
                                line=line_number,
                                reason=f"Unparseable credit {raw_credit!r}: {exc}",
                            )
                        )
                        continue

                if debit is None and credit is None:
                    failures.append(
                        ParseFailure(
                            file=str(file_path),
                            line=line_number,
                            reason="Both debit and credit are missing or empty",
                        )
                    )
                    continue

                description = _cell_value(raw_row, desc_idx)
                normalized_desc = fingerprint.normalize_description(description)
                fp_amount: Decimal = debit if debit is not None else credit  # type: ignore[assignment]

                txn_id = fingerprint.transaction_id(
                    source.account, txn_date, fp_amount, normalized_desc
                )
                occ = occurrence_counter.get(txn_id, 0)
                occurrence_counter[txn_id] = occ + 1

                transactions.append(
                    Transaction(
                        date=txn_date,
                        description=description,
                        debit=debit,
                        credit=credit,
                        account=source.account,
                        source_file=str(file_path),
                        txn_id=txn_id,
                        occurrence=occ,
                    )
                )

    return ParseResult(transactions=transactions, failures=failures)
