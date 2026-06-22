# docs-to-ledger

Scans a folder of bank statements (CSV/PDF), invoices, and receipts, then builds
or updates per-account spreadsheet ledgers with matched document links.

## Prerequisites

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — required only if
  you have image files or scanned PDFs. Install once system-wide:
  - **Windows:** download installer from the Tesseract GitHub releases page and
    add it to your PATH.
  - **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr`
  - **macOS:** `brew install tesseract`

## Install

```bash
pip install -e .[dev]
```

## Usage

```bash
docs-to-ledger <input_path> [--config docs-to-ledger.yaml] [--output-dir ledgers/] [--format xlsx] [--dry-run]
```

Copy `docs-to-ledger.example.yaml` to `docs-to-ledger.yaml` and edit to match
your folder layout before running.

## Development

```bash
pytest               # run tests
ruff check .         # lint
mypy docs_to_ledger  # type check
```
