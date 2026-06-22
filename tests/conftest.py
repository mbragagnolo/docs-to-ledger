"""Session-level fixture generation for binary test assets."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Minimal valid 3-object PDF (no content stream) with pre-computed xref offsets.
# Offsets verified manually: obj1@9, obj2@52, obj3@101, xref@164.
_MINIMAL_PDF: bytes = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n"
    b"0 4\n"
    b"0000000000 65535 f\r\n"
    b"0000000009 00000 n\r\n"
    b"0000000052 00000 n\r\n"
    b"0000000101 00000 n\r\n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n"
    b"164\n"
    b"%%EOF\n"
)


def _ensure_fixtures() -> None:
    FIXTURES.mkdir(exist_ok=True)

    pdf_path = FIXTURES / "sample_text.pdf"
    if not pdf_path.exists():
        pdf_path.write_bytes(_MINIMAL_PDF)

    png_path = FIXTURES / "sample_image.png"
    if not png_path.exists():
        from PIL import Image  # type: ignore[import-untyped]

        img = Image.new("RGB", (100, 50), color=(255, 255, 255))
        img.save(str(png_path))

    xlsx_path = FIXTURES / "sample_workbook.xlsx"
    if not xlsx_path.exists():
        import openpyxl  # type: ignore[import-untyped]

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "2026-06"
        ws.append(
            ["Date", "Description", "Debit", "Credit", "Account", "Transaction ID", "Imported At"]
        )
        ws.append(
            ["2026-06-15", "EXISTING ROW", "149.90", "", "SG Compte Courant",
             "abc123", "2026-06-01T10:00:00"]
        )
        wb.save(str(xlsx_path))


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    _ensure_fixtures()
