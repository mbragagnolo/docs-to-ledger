"""Statement parsing package.

Public API:
    parse_statement(file_path, source) -> ParseResult
    ParseResult
    ParseFailure
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docs_to_ledger.model import SourceRule, Transaction


@dataclass
class ParseFailure:
    """A non-fatal parsing error for a single row/entry."""

    file: str
    line: int
    reason: str


@dataclass
class ParseResult:
    """The outcome of parsing a single statement file."""

    transactions: list[Transaction] = field(default_factory=list)
    failures: list[ParseFailure] = field(default_factory=list)


def parse_statement(file_path: Path, source: SourceRule) -> ParseResult:
    """Dispatch to the appropriate parser based on source.statement_type.

    Raises ValueError for unknown statement types.
    """
    if source.statement_type == "csv":
        from docs_to_ledger.parsing.csv_parser import parse_csv

        return parse_csv(file_path, source)

    if source.statement_type == "pdf":
        from docs_to_ledger.parsing.pdf_sg import parse_pdf_sg

        return parse_pdf_sg(file_path, source)

    raise ValueError(f"Unsupported statement_type {source.statement_type!r}")


__all__ = ["ParseFailure", "ParseResult", "parse_statement"]
