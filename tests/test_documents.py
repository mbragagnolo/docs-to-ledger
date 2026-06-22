"""Tests for docs_to_ledger.documents and docs_to_ledger.ocr."""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from docs_to_ledger.errors import OcrUnavailableError
from docs_to_ledger.model import DocumentFeature

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# ocr.ensure_available
# ---------------------------------------------------------------------------


def test_ensure_available_raises_when_tesseract_missing() -> None:
    """ensure_available raises OcrUnavailableError when Tesseract is not found."""
    import docs_to_ledger.ocr as ocr

    with patch("pytesseract.get_tesseract_version", side_effect=OSError("not found")):
        with pytest.raises(OcrUnavailableError):
            ocr.ensure_available()


def test_ensure_available_succeeds_when_tesseract_present() -> None:
    """ensure_available returns None when Tesseract is found."""
    import docs_to_ledger.ocr as ocr

    with patch("pytesseract.get_tesseract_version", return_value="5.0.0"):
        result = ocr.ensure_available()
    assert result is None


# ---------------------------------------------------------------------------
# extract_features on text PDF (sample_text.pdf has no actual text)
# ---------------------------------------------------------------------------


def test_extract_features_text_pdf_returns_document_feature() -> None:
    """extract_features on a text PDF returns a DocumentFeature (not None)."""
    from docs_to_ledger import documents

    pdf_path = str(FIXTURES / "sample_text.pdf")
    result = documents.extract_features(pdf_path)
    assert result is not None
    assert isinstance(result, DocumentFeature)


def test_extract_features_text_pdf_no_ocr_called() -> None:
    """For a text PDF, ocr.run_ocr is never called (even with no usable text)."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    pdf_path = str(FIXTURES / "sample_text.pdf")
    with patch.object(ocr_mod, "run_ocr") as mock_run_ocr:
        documents.extract_features(pdf_path)
    mock_run_ocr.assert_not_called()


def test_extract_features_text_pdf_ensure_available_not_called() -> None:
    """For a text PDF, ocr.ensure_available is never called."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    pdf_path = str(FIXTURES / "sample_text.pdf")
    with patch.object(ocr_mod, "ensure_available") as mock_ensure:
        documents.extract_features(pdf_path)
    mock_ensure.assert_not_called()


def test_extract_features_text_pdf_no_text_returns_sentinel() -> None:
    """A text PDF with no usable text returns sentinel: amount=0, date=None, needs_ocr=True."""
    from docs_to_ledger import documents

    pdf_path = str(FIXTURES / "sample_text.pdf")
    result = documents.extract_features(pdf_path)
    assert result is not None
    # The fixture PDF has no real text content, so it should return sentinel
    assert result.amount == Decimal("0")
    assert result.date is None
    assert result.needs_ocr is True
    assert result.source_path == pdf_path


# ---------------------------------------------------------------------------
# extract_features on an image (mock OCR seam)
# ---------------------------------------------------------------------------


def test_extract_features_image_with_ocr_text() -> None:
    """When OCR returns text with amount and date, DocumentFeature has correct values."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")
    ocr_text = "Invoice from ACME Corp\nDate: 15/06/2026\nTotal: 149.90 EUR"

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value=ocr_text),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.amount == Decimal("149.90")
    assert result.date == datetime.date(2026, 6, 15)
    assert result.needs_ocr is True
    assert result.source_path == png_path


def test_extract_features_image_needs_ocr_true() -> None:
    """Image files always produce DocumentFeature with needs_ocr=True."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value="1234.56 some text"),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.needs_ocr is True


def test_extract_features_image_ocr_calls_ensure_available() -> None:
    """extract_features calls ensure_available for image files."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available") as mock_ensure,
        patch.object(ocr_mod, "run_ocr", return_value="100.00"),
    ):
        documents.extract_features(png_path)

    mock_ensure.assert_called_once()


# ---------------------------------------------------------------------------
# No-usable-content sentinel
# ---------------------------------------------------------------------------


def test_extract_features_no_amount_or_date_returns_sentinel() -> None:
    """When OCR returns text with no parseable amount or date, returns sentinel."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value="Hello world no amounts here"),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.amount == Decimal("0")
    assert result.date is None
    assert result.needs_ocr is True


def test_extract_features_ocr_empty_text_returns_sentinel() -> None:
    """When OCR returns empty text, returns sentinel."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value=""),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.amount == Decimal("0")
    assert result.date is None
    assert result.needs_ocr is True


# ---------------------------------------------------------------------------
# Image file routing by extension
# ---------------------------------------------------------------------------


def test_extract_features_png_routes_through_ocr() -> None:
    """A .png file routes through OCR path (ensure_available is called)."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available") as mock_ensure,
        patch.object(ocr_mod, "run_ocr", return_value="50.00"),
    ):
        documents.extract_features(png_path)

    mock_ensure.assert_called()


def test_extract_features_jpg_routes_through_ocr(tmp_path: Path) -> None:
    """A .jpg file routes through OCR path."""
    from PIL import Image  # type: ignore[import-untyped]

    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    jpg_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (100, 50), color=(255, 255, 255))
    img.save(str(jpg_path))

    with (
        patch.object(ocr_mod, "ensure_available") as mock_ensure,
        patch.object(ocr_mod, "run_ocr", return_value="75.00"),
    ):
        result = documents.extract_features(str(jpg_path))

    mock_ensure.assert_called()
    assert result is not None
    assert result.needs_ocr is True


def test_extract_features_jpeg_routes_through_ocr(tmp_path: Path) -> None:
    """A .jpeg file routes through OCR path."""
    from PIL import Image  # type: ignore[import-untyped]

    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    jpeg_path = tmp_path / "test.jpeg"
    img = Image.new("RGB", (100, 50), color=(200, 200, 200))
    img.save(str(jpeg_path))

    with (
        patch.object(ocr_mod, "ensure_available") as mock_ensure,
        patch.object(ocr_mod, "run_ocr", return_value="200.50"),
    ):
        result = documents.extract_features(str(jpeg_path))

    mock_ensure.assert_called()
    assert result is not None


def test_extract_features_text_pdf_routes_direct() -> None:
    """A PDF with text content routes through direct extraction (not OCR)."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    # Use a real text PDF - we'll mock pdfplumber to return text
    pdf_path = str(FIXTURES / "sample_text.pdf")

    with patch.object(ocr_mod, "ensure_available") as mock_ensure:
        with patch("pdfplumber.open") as mock_open:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Invoice 149.90 EUR\n15/06/2026"
            mock_pdf = MagicMock()
            mock_pdf.pages = [mock_page]
            mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
            mock_pdf.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_pdf

            result = documents.extract_features(pdf_path)

    mock_ensure.assert_not_called()
    assert result is not None
    assert result.amount == Decimal("149.90")
    assert result.date == datetime.date(2026, 6, 15)
    assert result.needs_ocr is False


# ---------------------------------------------------------------------------
# Return None on file-not-found
# ---------------------------------------------------------------------------


def test_extract_features_missing_file_returns_none() -> None:
    """extract_features returns None when the file does not exist."""
    from docs_to_ledger import documents

    result = documents.extract_features("/nonexistent/path/invoice.pdf")
    assert result is None


# ---------------------------------------------------------------------------
# Amount extraction: various formats
# ---------------------------------------------------------------------------


def test_extract_features_french_amount_format() -> None:
    """Amount extraction handles French format 1 234,56."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")
    ocr_text = "Date: 15/06/2026\nTotal: 1 234,56 EUR"

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value=ocr_text),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.amount == Decimal("1234.56")


def test_extract_features_takes_largest_amount() -> None:
    """When multiple amounts are found, the largest is taken."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")
    ocr_text = "Date 01/06/2026\nSub 10.00 Tax 5.00 Total 15.00"

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value=ocr_text),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.amount == Decimal("15.00")


# ---------------------------------------------------------------------------
# Date extraction: various formats
# ---------------------------------------------------------------------------


def test_extract_features_iso_date_format() -> None:
    """Date extraction handles ISO format yyyy-mm-dd."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value="Date 2026-06-15\nAmount 99.99"),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.date == datetime.date(2026, 6, 15)


def test_extract_features_dd_mm_yyyy_date_format() -> None:
    """Date extraction handles dd/mm/yyyy format."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value="Date 25/12/2025\nAmount 50.00"),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.date == datetime.date(2025, 12, 25)


def test_extract_features_dd_mm_yyyy_hyphen_date_format() -> None:
    """Date extraction handles dd-mm-yyyy format."""
    import docs_to_ledger.ocr as ocr_mod
    from docs_to_ledger import documents

    png_path = str(FIXTURES / "sample_image.png")

    with (
        patch.object(ocr_mod, "ensure_available"),
        patch.object(ocr_mod, "run_ocr", return_value="Date 03-07-2026\nAmount 88.88"),
    ):
        result = documents.extract_features(png_path)

    assert result is not None
    assert result.date == datetime.date(2026, 7, 3)
