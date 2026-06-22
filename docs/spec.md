# Spec: docs-to-ledger

## Summary
A Python command-line tool that scans a folder tree containing bank statements
(CSV and PDF), invoices, and receipts, then builds or updates per-account
spreadsheet ledgers. For each account it parses statement lines into a workbook
(one sheet per calendar month), then locates supporting documents anywhere in
the tree, matches each document to its transaction by amount and date, copies
the matched file into an organized archive, and links it from the ledger row.
Re-running is safe and idempotent. Unmatched and ambiguous items are surfaced on
a Review sheet rather than guessed.

## Inputs

### CLI
- `input_path` / string / **required** / Root folder to scan. Searched
  recursively (folder + all child folders) for both statements and documents.
- `--config` / path / optional (default `./docs-to-ledger.yaml`) / Config file
  (see below).
- `--output-dir` / path / optional / Where account workbooks and the archive
  are written. Default: alongside `input_path` (e.g. `<input_path>/ledgers/`).
- `--format` / enum `xlsx|ods` / optional (default `xlsx`) / Ledger file format.
- `--dry-run` / flag / optional / Parse, dedupe, and match, but write nothing;
  print a report of what *would* change.

### Config file (YAML) — *recommended default: YAML*
Holds everything that varies per environment so runs are repeatable/scriptable.
**v1 supports a single bank: Société Générale (SG).** The source/routing and
parsing-profile design is deliberately config-driven so additional banks can be
added later by adding entries and a parse profile — no code changes to the core.
- **Sources / account routing:** a list mapping each input source to an account.
  A source is identified by one of: a subfolder path, a filename glob/regex, or
  a value in a CSV column. Each entry specifies:
  - `account` — account name (also the workbook name).
  - `statement_type` — `csv` or `pdf`.
  - `locale` — date format (e.g. `dd/mm/yyyy`) and decimal separator
    (`comma` | `dot`). Configurable **per source**; falls back to the top-level
    **default locale: France** (`dd/mm/yyyy` dates, comma decimal separator,
    space/non-breaking-space thousands separator, e.g. `1 234,56`).
  - For CSV: `column_map` mapping the bank's column headers to canonical fields
    (date, description, debit, credit *or* signed amount, balance-ignored).
  - For PDF: a parsing template/profile identifying how to extract rows for that
    bank layout.
- **Matching:** `date_window_days` (default `3`), `amount_tolerance` (default
  `0` = exact to the cent), and fuzzy-text settings for tie-breaking.
- **Archive:** root folder name and layout (default year/month).

### Data read from disk
- **Statements:** CSV exports and PDF statements.
- **Documents:** invoices/receipts as PDF and image files (JPG, PNG, etc.).
  Image files and scanned (non-text) PDFs are read via OCR.

## Outputs

### Per-account ledger workbooks (`.xlsx` or `.ods`)
- **One workbook per account.**
- **One sheet per calendar month**, named by month (e.g. `2026-06`), with
  transactions placed on the sheet matching their own transaction date.
- A **`Review` sheet** in each workbook listing that account's unmatched
  transactions and any documents that matched nothing or matched ambiguously.

#### Transaction columns (per monthly sheet)
| Column | Meaning |
|---|---|
| Date | Transaction date |
| Description | Statement description / memo |
| Debit | Money out (blank if a credit) |
| Credit | Money in (blank if a debit) |
| Account | Account name (also the workbook) |
| Category | **Reserved, unused in v1** (placeholder for future rules-based categorization) |
| Document | Clickable hyperlink to the archived matched file (blank if none) |
| Archived Path | Path text of the archived file |
| Match Status | `matched` \| `unmatched` \| `ambiguous` |
| Confidence | Match score (0–1) |
| Source File | Statement file the row was parsed from |
| Transaction ID | Stable fingerprint used for idempotent dedupe (see Behavior) |
| Imported At | Timestamp of the run that first added the row |

### Document archive
- Matched documents are **copied** (originals left in place) into an organized
  archive laid out by **year/month**, e.g.
  `archive/2026/06/2026-06-15_149.90_vendor.pdf`.
  *(Filename convention `YYYY-MM-DD_amount_vendor.ext` is a recommended default;
  collisions get a numeric suffix.)*

### Console / report
- Summary per run: rows added, rows updated, documents matched, documents
  copied, items sent to Review.

## Behavior
High-level flow per run:

1. **Load config** and resolve the account routing rules.
2. **Discover files** by walking `input_path` recursively. Classify each file as
   a statement (CSV/PDF, per config) or a candidate document (PDF/image).
3. **Route statements to accounts** using the config-driven mapping (subfolder /
   filename pattern / CSV column value → account + parse rules + workbook).
4. **Parse statements** into canonical transaction records (date, description,
   debit, credit, source file), applying the source's locale for date and number
   parsing.
5. **Compute a fingerprint (Transaction ID)** for each parsed transaction from
   `account + date + amount + normalized description`, plus an **occurrence
   index** so that legitimately identical transactions (same date, amount, and
   description on one statement) are all kept, while re-importing the same
   statement does not create duplicates.
6. **Open or create** each account workbook. **Dedupe & merge:** rows whose
   Transaction ID + occurrence index already exist are left in place (preserving
   any manual edits / future categorization); genuinely new rows are added to the
   correct monthly sheet. The workbook itself is the source of truth for what has
   already been imported (no separate database).
7. **Extract document features:** for every candidate document, obtain a total
   amount and a date. Text-bearing PDFs are read directly; images and scanned
   PDFs are run through **local Tesseract OCR**. Optionally capture a vendor
   string for tie-breaking.
8. **Match documents to transactions** *within the same account*: a document
   matches a transaction when the amount is equal (within `amount_tolerance`,
   default exact) and the document date is within `date_window_days` (default
   ±3). When multiple transactions tie on amount/date, use fuzzy vendor-name
   similarity against the description to pick the best; if still ambiguous, mark
   `ambiguous`.
9. **On a confident unique match:** copy the document into the year/month
   archive, set the row's Document hyperlink + Archived Path, set Match Status =
   `matched`, and record Confidence.
10. **Surface leftovers on the Review sheet:** transactions with no document
    (Match Status `unmatched`) and documents that matched nothing or matched
    ambiguously, so a human can resolve them. Ambiguous documents are **not**
    auto-linked.
11. **Write** the workbook(s) in the configured format and print the run report.

## Edge cases
- **Empty input folder / no statements found** → no workbooks written; report
  says nothing to do (not an error).
- **Statement row that fails to parse** (bad date, unparseable amount) → skipped
  and reported; logged with file + line so it can be fixed. Does not abort the
  run.
- **File not attributable to any account** (no routing rule matches) → reported
  as "unrouted" and skipped; listed so config can be extended.
- **Transaction whose date can't be determined** → placed on the Review sheet
  rather than a monthly sheet.
- **Legitimately identical transactions** (same date/amount/description) → all
  kept via occurrence index; re-imports do not duplicate.
- **Document matches multiple transactions** → marked `ambiguous`, sent to
  Review, not linked.
- **Multiple documents match one transaction** → first/best linked; the others
  go to Review for manual attachment (one transaction holds one document link in
  v1).
- **OCR returns no usable amount/date** → document goes to Review as
  unmatchable, with a note.
- **Manual edits in an existing ledger** (e.g. a future category, a corrected
  description) → preserved across re-runs because dedupe matches on Transaction
  ID, not on the full row.
- **Same document already archived** (re-run) → detected by Transaction ID
  already linked; not re-copied.
- **Document amount present as a credit vs debit** → matching compares absolute
  amounts; expense documents are expected to map to the Debit side.

## Errors
- **Missing/invalid config** → fail fast with a clear message before any file is
  touched.
- **Tesseract not installed / not on PATH** → fail fast with install guidance
  *only if* image/scanned-PDF documents are present that require OCR; text-only
  runs proceed.
- **Output directory not writable / workbook locked open** → fail with a clear
  message; no partial corruption (write to temp then atomically replace).
- **Per-file parse/OCR failures** → non-fatal; collected and reported, run
  continues.
- General principle: configuration/environment problems abort early; per-record
  data problems degrade gracefully and are reported.

## Constraints & dependencies
- **Language/runtime:** Python (3.x).
- **Spreadsheets:** library supporting both `.xlsx` and `.ods` with hyperlink
  support (e.g. `openpyxl` for xlsx, `odfpy`/`ezodf` for ods, or `pandas` for
  parsing) — *recommended defaults, to be finalized at implementation.*
- **PDF text extraction:** e.g. `pdfplumber` / `pypdf` — *recommended default.*
- **OCR:** **local Tesseract** binary via `pytesseract` (offline, private;
  requires one-time Tesseract install). OCR step should be written so a cloud
  backend *could* be swapped in later, but only Tesseract ships in v1.
- **Images:** `Pillow` for image handling — *recommended default.*
- **Config:** YAML — *recommended default.*
- **Platform:** cross-platform; primary dev/use on Windows.
- **Non-destructive:** original statements and documents are never moved or
  modified; documents are *copied* into the archive.

## Open questions / assumptions
*(Items marked **[default]** were chosen as recommended defaults, not explicitly
confirmed by the user.)*

- **[default]** Full column set beyond Debit/Credit (Category reserved,
  Confidence, Transaction ID, Imported At, Source File) — proposed and shown in
  summary, not objected to.
- **[default]** Fuzzy vendor-name similarity as the tie-breaker when amount+date
  produce multiple candidates.
- **[default]** Transaction fingerprint = `account + date + amount + normalized
  description` plus an occurrence index for true duplicates.
- **[default]** Archive filename convention `YYYY-MM-DD_amount_vendor.ext` with
  numeric suffix on collision.
- **[default]** Config format is YAML; default config path `./docs-to-ledger.yaml`.
- **[default]** Idempotency state lives in the workbook itself (Transaction ID
  column); no separate database/state file.
- **[default]** One transaction holds at most one document link in v1; extra
  matches go to Review.
- **CONFIRMED:** default `locale` is **France** (`dd/mm/yyyy`, comma decimal,
  space thousands separator). Still overridable per source.
- **CONFIRMED:** v1 targets a **single bank, Société Générale (SG)**; more banks
  to be added later via config + parse profiles.
- **PDF statement parsing is the highest-risk area:** it requires a per-bank
  layout profile. For v1 this means building/validating **one** profile for the
  SG statement layout (both the CSV export and PDF formats SG provides). The
  exact SG CSV column headers and PDF layout still need a sample to lock down
  before building the parser.
- **Confidence score scale/semantics** (how the 0–1 score is computed and the
  threshold separating `matched` from `ambiguous`) to be defined in
  implementation.
- **v1 explicitly excludes:** running-balance column, rules-based
  categorization, and multi-currency handling.
```
