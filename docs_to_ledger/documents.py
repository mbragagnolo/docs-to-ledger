"""Document feature extraction — amount, date, and optional vendor from candidate files."""
from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from docs_to_ledger import ocr
from docs_to_ledger.model import DocumentFeature

# Extensions treated as images (routed directly through OCR)
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Amounts: French space-thousands + comma decimal, or dot decimal, etc.
# Capture groups catch numbers like: 1 234,56 / 1234,56 / 1234.56 / 1 234.56
_AMOUNT_PATTERN = re.compile(
    r"\d{1,3}(?:[\s\xa0]\d{3})*[,\.]\d{2}"  # thousands-separated
    r"|"
    r"\d+[,\.]\d{2}",  # simple decimal
    re.UNICODE,
)

# Date patterns
_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),        # yyyy-mm-dd
    (re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"), "dmy_slash"),  # dd/mm/yyyy
    (re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b"), "dmy_hyphen"), # dd-mm-yyyy
]

# "Montant prélevé le 14 janvier 2026 32,34" — common in French telecom/utility invoices.
# The `.` after pr and lev handles accented variants (é encodes as a single byte/char).
_PRELEVEMENT_RE = re.compile(
    r"pr.lev.\s+(?:sur\s+)?le\s+(\d{1,2})\s+(\S+)\s+(\d{4})\s+"
    r"((?:\d[\d\s\xa0]*)?(?:\d[\d\.]*),\d{2})",
    re.IGNORECASE,
)

# Regex patterns for French month names — uses `.` where accented chars appear so that
# encoding artifacts (e.g. pdfplumber rendering é as Ø) are still matched.
_MONTH_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"^janv(?:ier)?\.?$", re.I), 1),
    (re.compile(r"^f.vr(?:ier)?\.?$", re.I), 2),   # é can be garbled
    (re.compile(r"^mars$", re.I), 3),
    (re.compile(r"^avr(?:il)?\.?$", re.I), 4),
    (re.compile(r"^mai$", re.I), 5),
    (re.compile(r"^juin$", re.I), 6),
    (re.compile(r"^juil(?:let)?\.?$", re.I), 7),
    (re.compile(r"^ao.t$", re.I), 8),               # û can be garbled
    (re.compile(r"^sept(?:embre)?\.?$", re.I), 9),
    (re.compile(r"^oct(?:obre)?\.?$", re.I), 10),
    (re.compile(r"^nov(?:embre)?\.?$", re.I), 11),
    (re.compile(r"^d.c(?:embre)?\.?$", re.I), 12),  # é can be garbled
]


def _parse_french_month(name: str) -> int | None:
    """Return 1-12 for a French month name.

    Uses regex with `.` in accent positions so that PDF encoding artifacts
    (e.g. é rendered as Ø by pdfplumber font-mapping bugs) are still matched.
    """
    clean = name.strip()
    for pattern, num in _MONTH_PATTERNS:
        if pattern.match(clean):
            return num
    return None


def _parse_prelevement_amount(raw: str) -> Decimal | None:
    """Parse a French-format amount string from a 'prélevé le' line."""
    clean = raw.replace("\xa0", "").replace(" ", "")
    if "," in clean:
        # Remove dot thousands separator, convert decimal comma to dot
        clean = clean.replace(".", "").replace(",", ".")
    try:
        return Decimal(clean)
    except InvalidOperation:
        return None


def _extract_prelevment_features(text: str) -> tuple[datetime.date, Decimal] | None:
    """Return (debit_date, amount) from the first 'prélevé le DD MMMM YYYY AMOUNT' line.

    Common in French telecom/utility invoices (Bouygues, SFR, EDF, etc.).
    Takes precedence over generic extraction because it gives the exact bank debit date
    and amount rather than the invoice issue date and invoice total.
    """
    m = _PRELEVEMENT_RE.search(text)
    if m is None:
        return None
    day_str, month_str, year_str, amount_str = (
        m.group(1), m.group(2), m.group(3), m.group(4)
    )
    month_num = _parse_french_month(month_str)
    if month_num is None:
        return None
    try:
        date = datetime.date(int(year_str), month_num, int(day_str))
    except ValueError:
        return None
    amount = _parse_prelevement_amount(amount_str)
    if amount is None:
        return None
    return date, amount


def _extract_amount(text: str) -> Decimal | None:
    """Find the largest Decimal number in *text* using amount patterns."""
    matches = _AMOUNT_PATTERN.findall(text)
    best: Decimal | None = None
    for raw in matches:
        # Normalise: remove whitespace/nbsp thousands separators, convert comma decimal → dot
        normalised = raw.replace("\xa0", "").replace(" ", "")
        # If comma is the last separator before 2 decimal digits, treat it as decimal point
        normalised = normalised.replace(",", ".")
        try:
            value = Decimal(normalised)
        except InvalidOperation:
            continue
        if best is None or value > best:
            best = value
    return best


def _extract_date(text: str) -> datetime.date | None:
    """Find the first parseable date in *text*."""
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(text)
        if m is None:
            continue
        try:
            if fmt == "iso":
                year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:  # dmy_slash or dmy_hyphen
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime.date(year, month, day)
        except ValueError:
            continue
    return None


def _is_barcode_line(line: str) -> bool:
    """Return True for 2D-DOC markers, barcode data, and uninformative short tokens."""
    if line == "2D-DOC":
        return True
    # Single character or pure-digit lines (page numbers etc.)
    if len(line) <= 2 or line.isdigit():
        return True
    # Long string without spaces (binary/encoded data)
    if len(line) > 40 and " " not in line:
        return True
    tokens = line.split()
    # Barcode data: many long all-uppercase-letter tokens (e.g. Bouygues 2D-DOC blocks)
    return len(tokens) >= 4 and all(
        len(t) > 15 and t.isupper() and t.isalpha() for t in tokens
    )


def _extract_vendor(text: str) -> str | None:
    """Extract vendor — first non-empty, non-barcode line of text."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _is_barcode_line(stripped):
            continue
        return stripped
    return None


def _features_from_text(source_path: str, text: str, needs_ocr: bool) -> DocumentFeature:
    """Build a DocumentFeature from *text*; fall back to sentinel values when nothing found."""
    # Prefer the 'prélevé le' line: gives exact bank debit date and amount.
    prelevment = _extract_prelevment_features(text)
    if prelevment is not None:
        date, amount = prelevment
    else:
        amount = _extract_amount(text)
        date = _extract_date(text)

    vendor = _extract_vendor(text) if text.strip() else None

    if amount is None or date is None:
        # Sentinel for Review: incomplete extraction
        return DocumentFeature(
            source_path=source_path,
            amount=Decimal("0"),
            date=None,
            vendor=vendor,
            needs_ocr=True,
        )

    return DocumentFeature(
        source_path=source_path,
        amount=amount,
        date=date,
        vendor=vendor,
        needs_ocr=needs_ocr,
    )


def _is_text_pdf(file_path: str) -> tuple[bool, str]:
    """Open a PDF with pdfplumber and return (has_text, combined_text).

    A PDF is considered a *text PDF* when at least one page yields non-whitespace text.
    """
    import pdfplumber

    combined: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text: str | None = page.extract_text()
            if page_text and page_text.strip():
                combined.append(page_text)

    full_text = "\n".join(combined)
    return bool(full_text.strip()), full_text


def extract_features(file_path: str | Path) -> DocumentFeature | None:
    """Extract amount, date, optional vendor from a candidate document.

    - For text PDFs (pdfplumber finds text): extract directly, no OCR.
    - For images (.png, .jpg, .jpeg, .tiff, .bmp): call ocr.ensure_available() then ocr.run_ocr().
    - For scanned/non-text PDFs: call ocr.ensure_available() then ocr.run_ocr() on pages.
    - If no usable amount/date can be recovered: return DocumentFeature with needs_ocr=True,
      amount=Decimal("0"), date=None (sentinel for Review).

    Returns None only on unrecoverable IO error (file not found).
    """
    path = Path(file_path)
    source_path = str(file_path)

    if not path.exists():
        return None

    suffix = path.suffix.lower()

    # --- Image files ---
    if suffix in _IMAGE_EXTENSIONS:
        ocr.ensure_available()
        text = ocr.run_ocr(source_path)
        return _features_from_text(source_path, text, needs_ocr=True)

    # --- PDF files ---
    if suffix == ".pdf":
        try:
            has_text, text = _is_text_pdf(source_path)
        except Exception:
            # Unreadable PDF — return sentinel without calling OCR
            return DocumentFeature(
                source_path=source_path,
                amount=Decimal("0"),
                date=None,
                vendor=None,
                needs_ocr=True,
            )

        if has_text:
            # Text PDF — extract directly, no OCR
            return _features_from_text(source_path, text, needs_ocr=False)

        # PDF with no extractable text layer (possibly scanned or empty).
        # Mark as needing OCR for review but do not call OCR eagerly here;
        # OCR should be triggered by a separate pipeline step that can handle
        # batch conversion via pdf_to_images + run_ocr.
        return _features_from_text(source_path, text, needs_ocr=True)

    # --- Unknown / unsupported extension ---
    # Return sentinel
    return DocumentFeature(
        source_path=source_path,
        amount=Decimal("0"),
        date=None,
        vendor=None,
        needs_ocr=True,
    )
