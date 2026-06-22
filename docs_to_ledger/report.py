"""Run report rendering."""
from __future__ import annotations

from docs_to_ledger.model import RunReport


def render(report: RunReport, dry_run: bool = False) -> str:
    """Format a RunReport as a human-readable summary."""
    header = (
        "=== docs-to-ledger DRY RUN summary ==="
        if dry_run
        else "=== docs-to-ledger run summary ==="
    )
    lines = [
        header,
        f"  Rows added:       {report.rows_added}",
        f"  Rows updated:     {report.rows_updated}",
        f"  Docs matched:     {report.docs_matched}",
        f"  Docs copied:      {report.docs_copied}",
        f"  Review items:     {report.review_items}",
        f"  Unrouted files:   {report.unrouted}",
        f"  Parse failures:   {report.parse_failures}",
    ]
    return "\n".join(lines)
