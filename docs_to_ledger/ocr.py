"""OCR boundary module — wraps Tesseract so the rest of the codebase stays clean.

A cloud backend could replace this module without touching documents.py.
"""
from __future__ import annotations

import os
import tempfile

import pytesseract
from PIL import Image

from docs_to_ledger.errors import OcrUnavailableError


def ensure_available() -> None:
    """Raise OcrUnavailableError with install guidance if Tesseract is not on PATH.

    Call this lazily — only when OCR is actually needed.
    Never call it for text-only PDFs.
    """
    try:
        pytesseract.get_tesseract_version()
    except OSError as exc:
        raise OcrUnavailableError(
            "Tesseract is not installed or not on PATH. "
            "Install it from https://github.com/tesseract-ocr/tesseract "
            "and ensure the 'tesseract' executable is accessible."
        ) from exc


def run_ocr(image_path: str) -> str:
    """Run Tesseract OCR on the image at image_path, return extracted text."""
    img = Image.open(image_path)
    text: str = pytesseract.image_to_string(img)
    return text


def pdf_to_images(pdf_path: str) -> list[str]:
    """Convert a scanned PDF to a list of temp image paths for OCR.

    Tries pdf2image first if available, falls back to Pillow.
    Returns empty list if conversion fails gracefully.
    """
    # Try pdf2image first if available
    try:
        import pdf2image

        pages = pdf2image.convert_from_path(pdf_path)
        image_paths: list[str] = []
        for i, page in enumerate(pages):
            fd, tmp_path = tempfile.mkstemp(suffix=f"_page{i}.png")
            os.close(fd)
            page.save(tmp_path, "PNG")
            image_paths.append(tmp_path)
        return image_paths
    except ImportError:
        pass
    except Exception:
        return []

    # Fallback: try to open with Pillow directly (works for some PDFs)
    try:
        img = Image.open(pdf_path)
        image_paths = []
        for i in range(getattr(img, "n_frames", 1)):
            img.seek(i)
            fd, tmp_path = tempfile.mkstemp(suffix=f"_page{i}.png")
            os.close(fd)
            img.save(tmp_path, "PNG")
            image_paths.append(tmp_path)
        return image_paths
    except Exception:
        return []
