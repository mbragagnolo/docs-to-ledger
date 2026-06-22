"""Orchestrator: wire all Wave-1 components into the 11-step run flow."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from docs_to_ledger.archive import archive_document
from docs_to_ledger.config import load_config
from docs_to_ledger.discovery import discover
from docs_to_ledger.documents import extract_features
from docs_to_ledger.ledger import LedgerWorkbook
from docs_to_ledger.matching import match
from docs_to_ledger.model import DocumentFeature, MatchStatus, RunReport, Transaction
from docs_to_ledger.parsing import parse_statement


@dataclass
class RunArgs:
    input_path: Path
    config_path: Path
    output_dir: Path | None = None
    format: Literal["xlsx", "ods"] = "xlsx"
    dry_run: bool = False


def run(args: RunArgs) -> RunReport:
    """Execute the 11-step docs-to-ledger flow and return a RunReport.

    Raises ConfigError, OcrUnavailableError, or OutputWriteError on
    configuration / environment problems; per-record failures are collected
    in the returned RunReport.
    """
    report = RunReport()

    # Step 1: Load config — raises ConfigError on failure
    config = load_config(args.config_path)

    output_dir = args.output_dir or (args.input_path / "ledgers")
    fmt: Literal["xlsx", "ods"] = args.format

    # Step 2: Discover files
    discovered = discover(args.input_path, config)
    report.unrouted = len(discovered.unrouted)

    # Steps 3+4: Route + parse all statements; group transactions by account
    account_txns: dict[str, list[Transaction]] = {}
    for file_path, source_rule in discovered.statements:
        result = parse_statement(file_path, source_rule)
        report.parse_failures += len(result.failures)
        for txn in result.transactions:
            account_txns.setdefault(txn.account, []).append(txn)

    if not account_txns:
        return report

    # Create output directory only when we have data to write (and are not dry-running)
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Step 7: Extract document features from candidate files
    candidate_docs: list[DocumentFeature] = []
    for doc_path in discovered.candidate_docs:
        feature = extract_features(doc_path)
        if feature is not None:
            candidate_docs.append(feature)

    # Resolve archive root to an absolute path so archive_document writes
    # relative to output_dir rather than the process working directory.
    archive_root = config.archive.root
    if not Path(archive_root).is_absolute():
        archive_root = str(output_dir / archive_root)
    archive_settings = dataclasses.replace(config.archive, root=archive_root)

    # Steps 5–11: Per-account workbook processing
    for account, transactions in account_txns.items():
        wb_path = output_dir / f"{account}.{fmt}"
        wb = LedgerWorkbook(wb_path, fmt)
        wb.open_or_create()

        # Steps 5+6: Fingerprints already assigned by the parser; upsert skips
        # rows whose (txn_id, occurrence) key is already present.
        rows_added, rows_updated = wb.upsert(transactions)
        report.rows_added += rows_added
        report.rows_updated += rows_updated

        # Step 8: Match documents to this account's transactions
        outcome = match(transactions, candidate_docs, config.matching)
        report.docs_matched += len(outcome.links)

        if not args.dry_run:
            # Step 9: Archive + link confident matches
            for (txn_id, occ), (feature, confidence) in outcome.links.items():
                archived_path = archive_document(feature, archive_settings)
                report.docs_copied += 1
                wb.set_match(
                    key=(txn_id, occ),
                    document_link=archived_path,
                    archived_path=archived_path,
                    status=MatchStatus.matched,
                    confidence=confidence,
                )
        else:
            report.docs_copied += len(outcome.links)

        # Step 10: Surface leftovers on the Review sheet
        review_items: list[str] = []
        for txn in outcome.unmatched_txns:
            review_items.append(f"Unmatched transaction: {txn.date} | {txn.description}")
        for doc in outcome.ambiguous_docs:
            review_items.append(f"Ambiguous document: {doc.source_path}")
        for doc in outcome.unmatchable_docs:
            if doc.needs_ocr:
                review_items.append(f"Unmatchable (OCR/no amount+date): {doc.source_path}")
            else:
                review_items.append(f"Unmatchable document: {doc.source_path}")

        if review_items:
            if not args.dry_run:
                wb.add_to_review(review_items)
            report.review_items += len(review_items)

        # Step 11: Write workbook atomically
        if not args.dry_run:
            wb.save_atomic()

    return report
