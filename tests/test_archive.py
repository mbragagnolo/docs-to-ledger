"""Tests for docs_to_ledger.archive module (Task 15)."""
from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

from docs_to_ledger.archive import archive_document
from docs_to_ledger.model import ArchiveSettings, DocumentFeature


def _make_feature(
    tmp_path: Path,
    *,
    filename: str = "receipt.pdf",
    content: bytes = b"fake pdf content",
    date: datetime.date | None = datetime.date(2026, 6, 15),
    amount: Decimal = Decimal("149.90"),
    vendor: str | None = "Super U",
) -> DocumentFeature:
    src = tmp_path / filename
    src.write_bytes(content)
    return DocumentFeature(
        source_path=str(src),
        amount=amount,
        date=date,
        vendor=vendor,
        needs_ocr=False,
    )


def _settings(tmp_path: Path, layout: str = "year/month") -> ArchiveSettings:
    return ArchiveSettings(root=str(tmp_path / "archive"), layout=layout)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Basic archive
# ---------------------------------------------------------------------------


def test_basic_archive_creates_file(tmp_path: Path) -> None:
    """Archived file appears at the expected path under root/YYYY/MM/."""
    feature = _make_feature(tmp_path)
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    expected = Path(settings.root) / "2026" / "06" / "2026-06-15_149.90_super_u.pdf"
    assert expected.exists(), f"Expected {expected} to exist"
    assert Path(result) == expected


def test_basic_archive_preserves_source(tmp_path: Path) -> None:
    """Source file is untouched after archiving."""
    content = b"original content"
    feature = _make_feature(tmp_path, content=content)
    settings = _settings(tmp_path)

    archive_document(feature, settings)

    src = Path(feature.source_path)
    assert src.exists(), "Source file must still exist after archive"
    assert src.read_bytes() == content, "Source file content must be unchanged"


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------


def test_return_value_is_string(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path)
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert isinstance(result, str), "archive_document must return a str"


def test_return_value_points_to_copied_file(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path)
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert Path(result).exists(), f"Returned path {result!r} must exist"
    assert Path(result).read_bytes() == b"fake pdf content"


# ---------------------------------------------------------------------------
# Vendor None
# ---------------------------------------------------------------------------


def test_vendor_none_omits_vendor_part(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, vendor=None)
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    expected = Path(settings.root) / "2026" / "06" / "2026-06-15_149.90.pdf"
    assert expected.exists()
    assert Path(result) == expected


# ---------------------------------------------------------------------------
# Date None (undated)
# ---------------------------------------------------------------------------


def test_date_none_uses_undated_prefix(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, date=None)
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert Path(result).name.startswith("undated_"), (
        f"Expected filename to start with 'undated_', got {Path(result).name!r}"
    )


def test_date_none_flat_layout(tmp_path: Path) -> None:
    """With date=None and flat layout, file lands directly in root."""
    feature = _make_feature(tmp_path, date=None, vendor=None)
    settings = _settings(tmp_path, layout="flat")

    result = archive_document(feature, settings)

    assert Path(result).parent == Path(settings.root)
    assert Path(result).name.startswith("undated_")


# ---------------------------------------------------------------------------
# Collision handling
# ---------------------------------------------------------------------------


def test_collision_creates_numbered_suffix(tmp_path: Path) -> None:
    """Archiving a different file that maps to the same name appends _1."""
    feature1 = _make_feature(tmp_path, filename="receipt1.pdf", content=b"content A")
    settings = _settings(tmp_path)
    result1 = archive_document(feature1, settings)

    feature2 = _make_feature(tmp_path, filename="receipt2.pdf", content=b"content B")
    result2 = archive_document(feature2, settings)

    assert Path(result1).name == "2026-06-15_149.90_super_u.pdf"
    assert Path(result2).name == "2026-06-15_149.90_super_u_1.pdf"
    assert Path(result1).exists()
    assert Path(result2).exists()


def test_collision_increments_further(tmp_path: Path) -> None:
    """Third distinct file gets _2."""
    settings = _settings(tmp_path)
    for i, letter in enumerate(["A", "B", "C"]):
        feature = _make_feature(
            tmp_path, filename=f"receipt{i}.pdf", content=f"content {letter}".encode()
        )
        archive_document(feature, settings)

    archive_dir = Path(settings.root) / "2026" / "06"
    names = {p.name for p in archive_dir.iterdir()}
    assert "2026-06-15_149.90_super_u.pdf" in names
    assert "2026-06-15_149.90_super_u_1.pdf" in names
    assert "2026-06-15_149.90_super_u_2.pdf" in names


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_same_content_no_new_file(tmp_path: Path) -> None:
    """Archiving the same source twice does not create a second file."""
    content = b"identical content"
    feature = _make_feature(tmp_path, content=content)
    settings = _settings(tmp_path)

    result1 = archive_document(feature, settings)
    result2 = archive_document(feature, settings)

    archive_dir = Path(settings.root) / "2026" / "06"
    files = list(archive_dir.iterdir())
    assert len(files) == 1, f"Expected 1 file, found: {[f.name for f in files]}"
    assert result1 == result2


def test_idempotent_returns_existing_path(tmp_path: Path) -> None:
    """Second call with same content returns the same path as the first."""
    feature = _make_feature(tmp_path, content=b"same same same")
    settings = _settings(tmp_path)

    result1 = archive_document(feature, settings)
    result2 = archive_document(feature, settings)

    assert result1 == result2


# ---------------------------------------------------------------------------
# Year/month layout
# ---------------------------------------------------------------------------


def test_year_month_layout_creates_directories(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path)
    settings = _settings(tmp_path)

    archive_document(feature, settings)

    year_dir = Path(settings.root) / "2026"
    month_dir = year_dir / "06"
    assert year_dir.is_dir()
    assert month_dir.is_dir()


def test_year_month_layout_correct_month_padding(tmp_path: Path) -> None:
    """Month is zero-padded to 2 digits."""
    feature = _make_feature(tmp_path, date=datetime.date(2026, 1, 5), filename="jan.pdf")
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert Path(result).parent.name == "01"


# ---------------------------------------------------------------------------
# Flat layout
# ---------------------------------------------------------------------------


def test_flat_layout_puts_file_in_root(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path)
    settings = _settings(tmp_path, layout="flat")

    result = archive_document(feature, settings)

    assert Path(result).parent == Path(settings.root)


# ---------------------------------------------------------------------------
# Non-destructive
# ---------------------------------------------------------------------------


def test_source_not_moved(tmp_path: Path) -> None:
    """archive_document must copy, not move."""
    feature = _make_feature(tmp_path)
    src = Path(feature.source_path)
    settings = _settings(tmp_path)

    archive_document(feature, settings)

    assert src.exists(), "Source file must NOT be moved"


def test_source_content_unchanged(tmp_path: Path) -> None:
    original = b"do not modify me"
    feature = _make_feature(tmp_path, content=original)
    settings = _settings(tmp_path)

    archive_document(feature, settings)

    assert Path(feature.source_path).read_bytes() == original


# ---------------------------------------------------------------------------
# Vendor name normalisation
# ---------------------------------------------------------------------------


def test_vendor_spaces_replaced_with_underscores(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, vendor="Super U")
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert "super_u" in Path(result).name


def test_vendor_special_chars_removed(tmp_path: Path) -> None:
    """Non-alphanumeric characters in vendor name are removed/replaced."""
    feature = _make_feature(tmp_path, vendor="Café & Co.")
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    name = Path(result).name
    # should not contain raw special chars from vendor
    assert "&" not in name
    assert "co." not in Path(result).stem.lower()  # trailing dot in "Co." should be stripped


def test_vendor_lowercased(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, vendor="AMAZON")
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert "amazon" in Path(result).name
    assert "AMAZON" not in Path(result).name


# ---------------------------------------------------------------------------
# Extension preservation
# ---------------------------------------------------------------------------


def test_extension_preserved_jpg(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, filename="receipt.jpg")
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert Path(result).suffix == ".jpg"


def test_extension_preserved_png(tmp_path: Path) -> None:
    feature = _make_feature(tmp_path, filename="receipt.png")
    settings = _settings(tmp_path)

    result = archive_document(feature, settings)

    assert Path(result).suffix == ".png"
