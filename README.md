# docs-to-ledger

Scans a folder of bank statements (CSV/PDF), invoices, and receipts, then builds
or updates per-account spreadsheet ledgers with matched document links. Re-running
is safe and idempotent — no rows are duplicated and no files are overwritten.

## Prerequisites

- **Python 3.10+**
- **[Tesseract OCR](https://github.com/tesseract-ocr/tesseract)** — required only
  when your input contains image files (`.png`, `.jpg`, etc.) or scanned PDFs.
  Text PDFs and CSV exports work without Tesseract. Install once, system-wide:

  | Platform | Command |
  |---|---|
  | Windows | Download from [UB-Mannheim Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki), install, and add to `PATH` |
  | Ubuntu/Debian | `sudo apt-get install tesseract-ocr` |
  | macOS | `brew install tesseract` |

## Install

```bash
pip install -e .
```

For development (tests, lint, type checking):

```bash
pip install -e ".[dev]"
```

## Quick start

1. Copy the sample config and edit it for your folder layout:

   ```bash
   cp docs-to-ledger.yaml my-config.yaml
   ```

2. Run against your input folder:

   ```bash
   docs-to-ledger /path/to/bank-exports --config my-config.yaml --output-dir ledgers/
   ```

3. Check the output — one `.xlsx` workbook per account, with a **Review** sheet
   listing anything that could not be matched automatically.

## CLI reference

```
docs-to-ledger <input_path> [OPTIONS]

Arguments:
  input_path          Root folder to scan recursively for statements and documents.

Options:
  --config PATH       Config file (default: ./docs-to-ledger.yaml).
  --output-dir PATH   Where to write workbooks and the archive
                      (default: <input_path>/ledgers/).
  --format xlsx|ods   Spreadsheet format (default: xlsx).
  --dry-run           Parse, match, and report what *would* change — writes nothing.
```

### --dry-run

Use `--dry-run` to preview results without touching any files:

```bash
docs-to-ledger /path/to/bank-exports --dry-run
```

Output:

```
Dry-run — nothing written.
Rows that would be added:   12
Documents that would match:  7
Documents that would copy:   7
Items for Review:            5
```

## Config file format

The YAML config drives everything that varies per environment.

```yaml
# docs-to-ledger.yaml

sources:
  # --- CSV statement from Société Générale ---
  - account: "SG Compte Courant"
    statement_type: csv
    path_pattern: "**/*.csv"          # relative glob matched against file paths
    locale:
      date_format: "dd/mm/yyyy"
      decimal_separator: comma         # French format: 1 234,56
      thousands_separator: space
    column_map:
      date: "Date de l'operation"      # map your bank's CSV column names here
      description: "Libelle"
      debit: "Debit"
      credit: "Credit"

  # --- PDF statement from Société Générale ---
  - account: "SG Compte Courant"
    statement_type: pdf
    path_pattern: "Documents_*.pdf"
    locale:
      date_format: "dd/mm/yyyy"
      decimal_separator: comma
      thousands_separator: dot

matching:
  date_window_days: 3          # document date must be within ±3 days of transaction
  amount_tolerance: 0          # exact match to the cent (set e.g. 0.01 for tolerance)
  fuzzy_vendor: true           # use vendor name similarity to break ties

archive:
  root: "archive"              # where to copy matched documents
  layout: "year/month"         # creates archive/2026/06/2026-06-15_149.90_super_u.pdf
```

## Output structure

```
ledgers/
  SG Compte Courant.xlsx      ← one workbook per account
  archive/
    2026/
      06/
        2026-06-15_149.90_super_u.pdf
        2026-06-14_2500.00_virement_salaire.pdf
```

Each workbook has:
- **One sheet per calendar month** (`2026-06`, `2026-07`, …) with columns:
  Date · Description · Debit · Credit · Account · Category · Transaction ID ·
  Document · Archived Path · Match Status · Confidence · Imported At
- A **Review** sheet listing unmatched transactions and documents that could not
  be matched or were ambiguous.

## Edge cases handled automatically

| Situation | Behaviour |
|---|---|
| Empty input / no statements | No workbooks written; report says "nothing to do" |
| Unparseable CSV row | Skipped; logged with file + line number |
| File matches no routing rule | Reported as "unrouted"; skipped |
| Two identical transactions (same date/amount/description) | Both kept via occurrence index |
| One document matches multiple transactions | Marked ambiguous → Review |
| Multiple documents for one transaction | Best match linked; others → Review |
| OCR finds no amount or date | Document → Review as unmatchable |
| Re-run after manual category edit | Edit preserved (dedupe on Transaction ID) |
| Same document already in archive | Content-checked; not re-copied |

## Development

```bash
pytest               # run tests (246 tests)
ruff check .         # lint
mypy docs_to_ledger  # type check
```
