"""Integration tests for runner.run() — the full 11-step orchestration."""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from docs_to_ledger.errors import ConfigError
from docs_to_ledger.model import DocumentFeature
from docs_to_ledger.runner import RunArgs, run

# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_CONFIG = """\
sources:
  - account: "Test Account"
    statement_type: csv
    path_pattern: "statements/*.csv"
    locale:
      date_format: "dd/mm/yyyy"
      decimal_separator: comma
      thousands_separator: space
    column_map:
      date: "Date"
      description: "Libelle"
      debit: "Debit"
      credit: "Credit"
matching:
  date_window_days: 3
  amount_tolerance: 0
  fuzzy_vendor: true
archive:
  root: "archive"
  layout: "year/month"
"""

_CSV = (
    "Date;Libelle;Debit;Credit\n"
    "15/06/2026;SUPER U;-149,90;\n"
    "14/06/2026;VIREMENT SALAIRE;;2500,00\n"
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def tree(tmp_path: Path) -> dict[str, Path]:
    """Minimal input tree: config + statements CSV + placeholder receipt."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    stmts = tmp_path / "input" / "statements"
    stmts.mkdir(parents=True)
    (stmts / "bank.csv").write_text(_CSV, encoding="utf-8")

    docs_dir = tmp_path / "input" / "docs"
    docs_dir.mkdir()
    receipt = docs_dir / "receipt.pdf"
    receipt.write_bytes(b"%PDF-1.4 placeholder")  # content irrelevant; extract_features is mocked

    return {
        "config_path": config_path,
        "input_path": tmp_path / "input",
        "output_dir": tmp_path / "output",
        "receipt_path": receipt,
    }


def _args(tree: dict[str, Path], *, dry_run: bool = False, fmt: str = "xlsx") -> RunArgs:
    from typing import Literal, cast

    return RunArgs(
        input_path=tree["input_path"],
        config_path=tree["config_path"],
        output_dir=tree["output_dir"],
        format=cast("Literal['xlsx', 'ods']", fmt),
        dry_run=dry_run,
    )


def _receipt_feature(receipt_path: Path) -> DocumentFeature:
    """A DocumentFeature that should match the SUPER U transaction."""
    return DocumentFeature(
        source_path=str(receipt_path),
        amount=Decimal("149.90"),
        date=datetime.date(2026, 6, 15),
        vendor="SUPER U",
        needs_ocr=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_full_run_no_docs(tree: dict[str, Path]) -> None:
    """Run with no extractable docs writes workbook; all transactions go to Review."""
    with patch("docs_to_ledger.runner.extract_features", return_value=None):
        report = run(_args(tree))

    assert report.rows_added == 2
    assert report.rows_updated == 0
    assert report.docs_matched == 0
    assert report.docs_copied == 0
    assert report.review_items == 2  # both txns unmatched
    assert report.parse_failures == 0
    assert report.unrouted == 0

    wb_path = tree["output_dir"] / "Test Account.xlsx"
    assert wb_path.exists()


def test_full_run_with_matched_doc(tree: dict[str, Path]) -> None:
    """Run with a matching receipt archives the doc and links it; 1 txn goes to Review."""
    with patch("docs_to_ledger.runner.extract_features") as mock_ef:
        mock_ef.return_value = _receipt_feature(tree["receipt_path"])
        report = run(_args(tree))

    assert report.rows_added == 2
    assert report.docs_matched == 1
    assert report.docs_copied == 1
    assert report.review_items == 1  # VIREMENT SALAIRE unmatched

    archive_dir = tree["output_dir"] / "archive"
    assert archive_dir.exists()
    archived = list(archive_dir.rglob("*.pdf"))
    assert len(archived) == 1


def test_re_run_is_idempotent(tree: dict[str, Path]) -> None:
    """Second run adds 0 new rows (deduped by Transaction ID)."""
    with patch("docs_to_ledger.runner.extract_features", return_value=None):
        run(_args(tree))
        report2 = run(_args(tree))

    assert report2.rows_added == 0


def test_dry_run_writes_nothing(tree: dict[str, Path]) -> None:
    """--dry-run reports would-be rows but creates no files."""
    with patch("docs_to_ledger.runner.extract_features", return_value=None):
        report = run(_args(tree, dry_run=True))

    assert report.rows_added == 2  # would-be rows
    assert report.review_items == 2  # would-be review entries
    assert not tree["output_dir"].exists()  # nothing written


def test_dry_run_with_matched_doc_counts_copies(tree: dict[str, Path]) -> None:
    """--dry-run with a matchable doc counts docs_copied without writing files."""
    with patch("docs_to_ledger.runner.extract_features") as mock_ef:
        mock_ef.return_value = _receipt_feature(tree["receipt_path"])
        report = run(_args(tree, dry_run=True))

    assert report.docs_copied == 1
    assert not tree["output_dir"].exists()


def test_empty_input_returns_empty_report(tmp_path: Path) -> None:
    """Empty input directory produces no workbooks and no error."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    empty_input = tmp_path / "empty"
    empty_input.mkdir()

    report = run(
        RunArgs(
            input_path=empty_input,
            config_path=config_path,
            output_dir=tmp_path / "output",
        )
    )

    assert report.rows_added == 0
    assert report.docs_matched == 0
    assert not (tmp_path / "output").exists()


def test_config_error_propagates(tmp_path: Path) -> None:
    """Missing config raises ConfigError before any file is touched."""
    with pytest.raises(ConfigError):
        run(
            RunArgs(
                input_path=tmp_path,
                config_path=tmp_path / "nonexistent.yaml",
                output_dir=tmp_path / "output",
            )
        )


def test_unrouted_files_counted(tree: dict[str, Path]) -> None:
    """CSV files not matched by any source rule are counted as unrouted."""
    # Place a CSV in a path that doesn't match "statements/*.csv"
    extra = tree["input_path"] / "other.csv"
    extra.write_text("Date;Libelle\n15/06/2026;something\n", encoding="utf-8")

    with patch("docs_to_ledger.runner.extract_features", return_value=None):
        report = run(_args(tree))

    assert report.unrouted >= 1
