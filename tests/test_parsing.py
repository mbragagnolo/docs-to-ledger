"""Tests for docs_to_ledger.parsing — locale helpers, CSV parser, and SG PDF parser."""
from __future__ import annotations

import ast
import datetime
import importlib
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from docs_to_ledger.model import Locale, SourceRule
from docs_to_ledger.parsing import ParseFailure, ParseResult, parse_statement
from docs_to_ledger.parsing.csv_parser import parse_csv
from docs_to_ledger.parsing.locale import parse_amount, parse_date
from docs_to_ledger.parsing.pdf_sg import parse_pdf_sg

FIXTURES = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared locale fixture
# ---------------------------------------------------------------------------

FR_LOCALE = Locale(
    date_format="dd/mm/yyyy",
    decimal_separator="comma",
    thousands_separator="space",
)

SG_SOURCE = SourceRule(
    account="SG Compte Courant",
    statement_type="csv",
    locale=FR_LOCALE,
    path_pattern="statements/**/*.csv",
    column_map={"date": "Date", "description": "Libelle", "debit": "Debit", "credit": "Credit"},
)


# ===========================================================================
# Locale tests
# ===========================================================================


class TestParseAmount:
    def test_simple_positive(self) -> None:
        assert parse_amount("149,90", FR_LOCALE) == Decimal("149.90")

    def test_simple_negative(self) -> None:
        assert parse_amount("-149,90", FR_LOCALE) == Decimal("-149.90")

    def test_thousands_space(self) -> None:
        # Regular ASCII space (U+0020) as thousands separator
        assert parse_amount("1 234,56", FR_LOCALE) == Decimal("1234.56")

    def test_thousands_nbsp(self) -> None:
        # U+00A0 non-breaking space as thousands separator (common in French bank CSVs)
        nbsp = chr(0x00A0)
        assert parse_amount(f"1{nbsp}234,56", FR_LOCALE) == Decimal("1234.56")

    def test_integer_like(self) -> None:
        assert parse_amount("2500,00", FR_LOCALE) == Decimal("2500.00")

    def test_dot_decimal_locale(self) -> None:
        dot_locale = Locale(
            date_format="mm/dd/yyyy",
            decimal_separator="dot",
            thousands_separator="comma",
        )
        assert parse_amount("1,234.56", dot_locale) == Decimal("1234.56")


class TestParseDate:
    def test_dmy(self) -> None:
        assert parse_date("15/06/2026", FR_LOCALE) == datetime.date(2026, 6, 15)

    def test_mdy(self) -> None:
        mdy_locale = Locale(date_format="mm/dd/yyyy")
        assert parse_date("06/15/2026", mdy_locale) == datetime.date(2026, 6, 15)

    def test_ymd(self) -> None:
        ymd_locale = Locale(date_format="yyyy/mm/dd")
        assert parse_date("2026/06/15", ymd_locale) == datetime.date(2026, 6, 15)

    def test_bad_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_date("bad", FR_LOCALE)

    def test_wrong_format_raises(self) -> None:
        # ISO format does not match dd/mm/yyyy
        with pytest.raises(ValueError):
            parse_date("2026-06-15", FR_LOCALE)


# ===========================================================================
# CSV parser tests
# ===========================================================================


class TestParseCsvFixture:
    """Tests that parse the sample_sg.csv fixture end-to-end."""

    def test_returns_parse_result(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        assert isinstance(result, ParseResult)

    def test_three_transactions_no_failures(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        assert len(result.transactions) == 3
        assert len(result.failures) == 0

    def test_row1_carte_super_u(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        txn = result.transactions[0]
        assert txn.date == datetime.date(2026, 6, 15)
        assert txn.description == "CARTE SUPER U"
        assert txn.debit == Decimal("149.90")
        assert txn.credit is None

    def test_row2_virement_salaire(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        txn = result.transactions[1]
        assert txn.date == datetime.date(2026, 6, 14)
        assert txn.description == "VIREMENT SALAIRE"
        assert txn.debit is None
        assert txn.credit == Decimal("2500.00")

    def test_row3_carte_amazon(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        txn = result.transactions[2]
        assert txn.date == datetime.date(2026, 6, 10)
        assert txn.description == "CARTE AMAZON"
        assert txn.debit == Decimal("45.00")
        assert txn.credit is None

    def test_txn_id_is_64_char_hex(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        for txn in result.transactions:
            assert len(txn.txn_id) == 64
            assert all(c in "0123456789abcdef" for c in txn.txn_id)

    def test_account_and_source_file(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        for txn in result.transactions:
            assert txn.account == "SG Compte Courant"
            assert txn.source_file == str(FIXTURES / "sample_sg.csv")

    def test_occurrence_zero_for_unique_rows(self) -> None:
        result = parse_csv(FIXTURES / "sample_sg.csv", SG_SOURCE)
        for txn in result.transactions:
            assert txn.occurrence == 0


class TestParseCsvEdgeCases:
    """Edge-case tests using tmp_path CSVs."""

    def test_duplicate_rows_get_distinct_occurrences(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "dup.csv"
        csv_file.write_text(
            "Date;Libelle;Debit;Credit\n"
            "15/06/2026;CARTE SUPER U;-149,90;\n"
            "15/06/2026;CARTE SUPER U;-149,90;\n"
            "15/06/2026;CARTE SUPER U;-149,90;\n",
            encoding="utf-8",
        )
        result = parse_csv(csv_file, SG_SOURCE)
        assert len(result.transactions) == 3
        assert result.transactions[0].occurrence == 0
        assert result.transactions[1].occurrence == 1
        assert result.transactions[2].occurrence == 2
        # All should share the same txn_id base
        ids = {txn.txn_id for txn in result.transactions}
        assert len(ids) == 1

    def test_bad_date_produces_failure(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "baddate.csv"
        csv_file.write_text(
            "Date;Libelle;Debit;Credit\n"
            "NOT-A-DATE;CARTE SUPER U;-149,90;\n"
            "15/06/2026;VIREMENT SALAIRE;;2500,00\n",
            encoding="utf-8",
        )
        result = parse_csv(csv_file, SG_SOURCE)
        assert len(result.transactions) == 1
        assert len(result.failures) == 1
        assert isinstance(result.failures[0], ParseFailure)
        assert result.failures[0].line == 2  # data row 1 (1-indexed, after header)
        assert "date" in result.failures[0].reason.lower()

    def test_empty_debit_and_credit_produces_failure(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "nodebcred.csv"
        csv_file.write_text(
            "Date;Libelle;Debit;Credit\n"
            "15/06/2026;MYSTERY ROW;;\n"
            "14/06/2026;VIREMENT SALAIRE;;2500,00\n",
            encoding="utf-8",
        )
        result = parse_csv(csv_file, SG_SOURCE)
        assert len(result.transactions) == 1
        assert len(result.failures) == 1
        assert (
            "debit" in result.failures[0].reason.lower()
            or "credit" in result.failures[0].reason.lower()
        )

    def test_comma_delimiter_fallback(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "comma.csv"
        csv_file.write_text(
            "Date,Libelle,Debit,Credit\n"
            "15/06/2026,CARTE SUPER U,-149.90,\n",
            encoding="utf-8",
        )
        dot_locale = Locale(
            date_format="dd/mm/yyyy",
            decimal_separator="dot",
            thousands_separator="none",
        )
        source = SourceRule(
            account="Test",
            statement_type="csv",
            locale=dot_locale,
            column_map={
                "date": "Date",
                "description": "Libelle",
                "debit": "Debit",
                "credit": "Credit",
            },
        )
        result = parse_csv(csv_file, source)
        assert len(result.transactions) == 1
        assert result.transactions[0].debit == Decimal("149.90")


# ===========================================================================
# PDF SG parser tests
# ===========================================================================


class TestParsePdfSg:
    def test_empty_pdf_returns_empty_result(self) -> None:
        pdf_source = SourceRule(
            account="SG Compte Courant",
            statement_type="pdf",
            locale=FR_LOCALE,
            pdf_profile="sg",
        )
        result = parse_pdf_sg(FIXTURES / "sample_text.pdf", pdf_source)
        assert isinstance(result, ParseResult)
        assert len(result.transactions) == 0
        assert len(result.failures) == 0

    def test_no_ocr_import(self) -> None:
        """pdf_sg must not import pytesseract — it uses only pdfplumber."""
        mod_name = "docs_to_ledger.parsing.pdf_sg"
        # Remove cached module so we inspect the AST of the source file directly
        sys.modules.pop(mod_name, None)

        pdf_sg_path = (
            Path(__file__).parent.parent / "docs_to_ledger" / "parsing" / "pdf_sg.py"
        )
        source_code = pdf_sg_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code)
        import_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                import_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_names.append(node.module)
        assert "pytesseract" not in import_names, "pdf_sg.py must not import pytesseract"

        # Re-import cleanly so downstream tests can use it
        importlib.import_module(mod_name)


# ===========================================================================
# parse_statement dispatcher tests
# ===========================================================================


class TestParseStatementDispatcher:
    def test_dispatches_csv(self) -> None:
        result = parse_statement(FIXTURES / "sample_sg.csv", SG_SOURCE)
        assert isinstance(result, ParseResult)
        assert len(result.transactions) == 3

    def test_dispatches_pdf_sg(self) -> None:
        pdf_source = SourceRule(
            account="SG Compte Courant",
            statement_type="pdf",
            locale=FR_LOCALE,
            pdf_profile="sg",
        )
        result = parse_statement(FIXTURES / "sample_text.pdf", pdf_source)
        assert isinstance(result, ParseResult)

    def test_unknown_type_raises(self) -> None:
        bad_source = SourceRule(
            account="X",
            statement_type="csv",  # valid type required by Literal
            locale=FR_LOCALE,
        )
        # Manually override statement_type to an invalid value to test the error path
        object.__setattr__(bad_source, "statement_type", "ofx")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="Unsupported"):
            parse_statement(FIXTURES / "sample_sg.csv", bad_source)
