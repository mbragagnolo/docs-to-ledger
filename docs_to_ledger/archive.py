"""Document archive: copy matched documents into a structured archive directory."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from docs_to_ledger.model import ArchiveSettings, DocumentFeature


def _build_filename(feature: DocumentFeature, suffix: str) -> str:
    """Construct the archive filename (without collision suffix)."""
    date_str = feature.date.strftime("%Y-%m-%d") if feature.date else "undated"
    amount_str = str(feature.amount)
    if feature.vendor:
        vendor_str = re.sub(r"[^\w]", "_", feature.vendor.lower()).strip("_")
        vendor_str = re.sub(r"_+", "_", vendor_str)
        return f"{date_str}_{amount_str}_{vendor_str}{suffix}"
    return f"{date_str}_{amount_str}{suffix}"


def _resolve_path(target: Path) -> Path:
    """Return a non-colliding path: append _1, _2, … before extension if needed."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    counter = 1
    while True:
        candidate = target.parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _same_content(src: Path, dst: Path) -> bool:
    """Return True when src and dst have identical content (size then MD5)."""
    if src.stat().st_size != dst.stat().st_size:
        return False

    def _hash(p: Path) -> str:
        return hashlib.md5(p.read_bytes()).hexdigest()

    return _hash(src) == _hash(dst)


def _target_dir(feature: DocumentFeature, settings: ArchiveSettings) -> Path:
    """Resolve and create the destination directory."""
    if settings.layout == "year/month" and feature.date is not None:
        directory = (
            Path(settings.root)
            / str(feature.date.year)
            / f"{feature.date.month:02d}"
        )
    else:
        directory = Path(settings.root)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def archive_document(feature: DocumentFeature, settings: ArchiveSettings) -> str:
    """Copy a matched document into the archive structure.

    Returns the archived file path as a string (used in ledger cells).
    """
    src = Path(feature.source_path)
    suffix = src.suffix
    filename = _build_filename(feature, suffix)

    directory = _target_dir(feature, settings)
    canonical = directory / filename

    # Idempotency: if canonical path already exists and content matches, skip copy.
    if canonical.exists() and _same_content(src, canonical):
        return str(canonical)

    # Collision resolution: find a free path.
    target = _resolve_path(canonical)

    shutil.copy2(src, target)
    return str(target)
