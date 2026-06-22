import csv
import datetime
from decimal import Decimal
from pathlib import Path

import yaml

from docs_to_ledger.model import (
    ArchiveSettings,
    Config,
    DocumentFeature,
    Locale,
    MatchOutcome,
    MatchSettings,
    MatchStatus,
    RunReport,
    SourceRule,
    Transaction,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# MatchStatus
# ---------------------------------------------------------------------------


def test_match_status_values() -> None:
    assert MatchStatus.matched.value == "matched"
    assert MatchStatus.unmatched.value == "unmatched"
    assert MatchStatus.ambiguous.value == "ambiguous"


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------


def test_transaction_debit() -> None:
    t = Transaction(
        date=datetime.date(2026, 6, 15),
        description="CARTE SUPER U",
        debit=Decimal("149.90"),
        credit=None,
        account="SG Compte Courant",
        source_file="sg.csv",
        txn_id="abc123",
        occurrence=0,
    )
    assert t.debit == Decimal("149.90")
    assert t.credit is None


def test_transaction_credit() -> None:
    t = Transaction(
        date=datetime.date(2026, 6, 14),
        description="VIREMENT SALAIRE",
        debit=None,
        credit=Decimal("2500.00"),
        account="SG Compte Courant",
        source_file="sg.csv",
        txn_id="def456",
        occurrence=0,
    )
    assert t.credit == Decimal("2500.00")
    assert t.debit is None


# ---------------------------------------------------------------------------
# DocumentFeature
# ---------------------------------------------------------------------------


def test_document_feature() -> None:
    doc = DocumentFeature(
        source_path="invoices/invoice.pdf",
        amount=Decimal("149.90"),
        date=datetime.date(2026, 6, 15),
        vendor="Super U",
        needs_ocr=False,
    )
    assert doc.amount == Decimal("149.90")
    assert not doc.needs_ocr


def test_document_feature_no_date() -> None:
    doc = DocumentFeature(
        source_path="scan.png",
        amount=Decimal("45.00"),
        date=None,
        vendor=None,
        needs_ocr=True,
    )
    assert doc.date is None
    assert doc.needs_ocr


# ---------------------------------------------------------------------------
# Config types
# ---------------------------------------------------------------------------


def test_locale_defaults() -> None:
    locale = Locale()
    assert locale.date_format == "dd/mm/yyyy"
    assert locale.decimal_separator == "comma"
    assert locale.thousands_separator == "space"


def test_source_rule() -> None:
    rule = SourceRule(account="SG", statement_type="csv")
    assert rule.statement_type == "csv"
    assert rule.column_map == {}


def test_match_settings_defaults() -> None:
    ms = MatchSettings()
    assert ms.date_window_days == 3
    assert ms.amount_tolerance == Decimal("0")
    assert ms.fuzzy_vendor is True


def test_archive_settings_defaults() -> None:
    a = ArchiveSettings()
    assert a.root == "archive"
    assert a.layout == "year/month"


def test_config_construction() -> None:
    rule = SourceRule(account="SG", statement_type="csv")
    cfg = Config(sources=[rule])
    assert len(cfg.sources) == 1
    assert cfg.format == "xlsx"


# ---------------------------------------------------------------------------
# MatchOutcome / RunReport
# ---------------------------------------------------------------------------


def test_match_outcome_defaults() -> None:
    outcome = MatchOutcome()
    assert outcome.links == {}
    assert outcome.unmatched_txns == []


def test_run_report_defaults() -> None:
    report = RunReport()
    assert report.rows_added == 0
    assert report.parse_failures == 0


def test_run_report_counters() -> None:
    report = RunReport(rows_added=5, docs_matched=3, review_items=1)
    assert report.rows_added == 5
    assert report.docs_matched == 3


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def test_fixture_yaml_loads() -> None:
    data = yaml.safe_load((FIXTURES / "docs-to-ledger.yaml").read_text())
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_fixture_csv_loads() -> None:
    with open(FIXTURES / "sample_sg.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert len(rows) >= 3
    debits = [r for r in rows if r.get("Debit", "").strip()]
    credits = [r for r in rows if r.get("Credit", "").strip()]
    assert len(debits) >= 1
    assert len(credits) >= 1


def test_fixture_pdf_loads() -> None:
    import pdfplumber  # type: ignore[import-untyped]

    with pdfplumber.open(FIXTURES / "sample_text.pdf") as pdf:
        assert len(pdf.pages) >= 1


def test_fixture_image_loads() -> None:
    from PIL import Image  # type: ignore[import-untyped]

    img = Image.open(FIXTURES / "sample_image.png")
    assert img.size[0] > 0


def test_fixture_workbook_loads() -> None:
    import openpyxl  # type: ignore[import-untyped]

    wb = openpyxl.load_workbook(FIXTURES / "sample_workbook.xlsx")
    assert len(wb.sheetnames) >= 1
