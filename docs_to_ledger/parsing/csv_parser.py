"""CSV statement parser."""
from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

from docs_to_ledger import fingerprint
from docs_to_ledger.model import SourceRule, Transaction
from docs_to_ledger.parsing.locale import parse_amount, parse_date

from . import ParseFailure, ParseResult


def _detect_delimiter(header: str) -> str:
    """Return ';' if present in header, else ','."""
    return ";" if ";" in header else ","


def parse_csv(file_path: Path, source: SourceRule) -> ParseResult:
    """Parse a CSV bank statement into a ParseResult.

    - Auto-detects delimiter (semicolon first, then comma).
    - Uses source.column_map to identify columns.
    - Debit and credit values are converted to positive Decimal (abs).
    - Rows with unparseable dates produce a ParseFailure (row skipped).
    - Rows with both debit and credit absent/empty produce a ParseFailure.
    - Duplicate rows (same txn_id) receive incrementing occurrence indices.
    """
    raw = file_path.read_text(encoding="utf-8-sig")  # strips BOM if present
    lines = raw.splitlines()
    if not lines:
        return ParseResult(transactions=[], failures=[])

    delimiter = _detect_delimiter(lines[0])

    reader = csv.DictReader(io.StringIO(raw), delimiter=delimiter)

    col_map = source.column_map  # e.g. {"date": "Date", "description": "Libelle", ...}
    date_col = col_map.get("date", "date")
    desc_col = col_map.get("description", "description")
    debit_col = col_map.get("debit", "debit")
    credit_col = col_map.get("credit", "credit")

    transactions: list[Transaction] = []
    failures: list[ParseFailure] = []
    occurrence_counter: dict[str, int] = {}

    for data_row_index, row in enumerate(reader, start=1):
        line_number = data_row_index + 1  # +1 for the header line

        # ---- parse date ----
        raw_date = (row.get(date_col) or "").strip()
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

        # ---- parse debit / credit ----
        raw_debit = (row.get(debit_col) or "").strip()
        raw_credit = (row.get(credit_col) or "").strip()

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

        # ---- build transaction ----
        description = (row.get(desc_col) or "").strip()
        normalized_desc = fingerprint.normalize_description(description)

        # Amount used for fingerprinting: debit takes precedence over credit
        fp_amount: Decimal = debit if debit is not None else credit  # type: ignore[assignment]

        txn_id = fingerprint.transaction_id(source.account, txn_date, fp_amount, normalized_desc)
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
