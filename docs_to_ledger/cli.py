"""CLI entry point for docs-to-ledger."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal, cast

from docs_to_ledger.errors import ConfigError, OcrUnavailableError, OutputWriteError
from docs_to_ledger.report import render
from docs_to_ledger.runner import RunArgs, run


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the pipeline, print the report.

    Returns 0 on success, 1 on configuration or environment errors.
    """
    parser = argparse.ArgumentParser(
        prog="docs-to-ledger",
        description=(
            "Build per-account ledger workbooks from bank statements and matched documents."
        ),
    )
    parser.add_argument("input_path", help="Root folder to scan recursively.")
    parser.add_argument(
        "--config",
        default="docs-to-ledger.yaml",
        metavar="PATH",
        help="Config file path (default: ./docs-to-ledger.yaml).",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        metavar="PATH",
        help="Where to write workbooks and the archive (default: <input_path>/ledgers/).",
    )
    parser.add_argument(
        "--format",
        choices=["xlsx", "ods"],
        default="xlsx",
        help="Ledger file format (default: xlsx).",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Parse, match, and report without writing any files.",
    )

    ns = parser.parse_args(argv)

    fmt = cast("Literal['xlsx', 'ods']", ns.format)
    args = RunArgs(
        input_path=Path(ns.input_path),
        config_path=Path(ns.config),
        output_dir=Path(ns.output_dir) if ns.output_dir else None,
        format=fmt,
        dry_run=ns.dry_run,
    )

    try:
        report = run(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except OcrUnavailableError as exc:
        print(f"OCR unavailable: {exc}", file=sys.stderr)
        return 1
    except OutputWriteError as exc:
        print(f"Write error: {exc}", file=sys.stderr)
        return 1

    print(render(report, dry_run=ns.dry_run))
    return 0
