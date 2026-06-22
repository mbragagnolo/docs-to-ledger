"""File discovery and routing: walk an input directory, classify every file."""
from __future__ import annotations

import csv
import fnmatch
import io
from dataclasses import dataclass, field
from pathlib import Path

from docs_to_ledger.model import Config, SourceRule

# Extensions that are always candidate documents (receipts, invoices, etc.)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


@dataclass
class DiscoveredFiles:
    """Result of a recursive directory scan."""

    statements: list[tuple[Path, SourceRule]] = field(default_factory=list)
    """CSV or PDF files matched to a SourceRule."""

    candidate_docs: list[Path] = field(default_factory=list)
    """PDFs or images that are not matched to any source rule."""

    unrouted: list[Path] = field(default_factory=list)
    """CSV (or PDF) files that could not be matched to any source rule."""

    ignored: list[Path] = field(default_factory=list)
    """Everything else (e.g. .txt, .yaml, .json)."""


def _match_pattern(file_path: Path, pattern: str) -> bool:
    """Return True if *any* trailing sub-path of file_path matches *pattern*.

    The pattern is treated as a relative glob (e.g. ``statements/**/*.csv``).
    Both path and pattern are compared as forward-slash strings so that
    fnmatch works correctly on all platforms, including Windows.

    Strategy: for each possible starting position in the path parts, join the
    remaining parts with ``/`` and check against the pattern using fnmatch.
    This lets a relative pattern match regardless of the absolute prefix on disk.

    Note: fnmatch treats ``**`` the same as ``*`` (both match any characters
    including ``/`` when the comparison string is flat), which is sufficient
    for patterns like ``statements/**/*.csv``.

    Examples::

        /home/user/data/statements/2026/june.csv  matched by  statements/**/*.csv
        C:\\Users\\me\\statements\\file.csv        matched by  statements/*.csv
    """
    # Convert to a sequence of non-root, non-anchor parts using forward slashes.
    # Path.parts includes the drive (e.g. 'C:\\') and anchor (e.g. '\\') on Windows,
    # or the root '/' on POSIX. We drop any parts that are also in Path.anchor.
    anchor_parts: set[str] = set()
    if file_path.drive:
        anchor_parts.add(file_path.drive)
    if file_path.root:
        anchor_parts.add(file_path.root)
    # Also include the combined anchor string (e.g. 'C:\\' already covers both on Windows).
    anchor_parts.add(file_path.anchor)

    meaningful_parts = [p for p in file_path.parts if p not in anchor_parts]

    for start in range(len(meaningful_parts)):
        candidate_str = "/".join(meaningful_parts[start:])
        if fnmatch.fnmatch(candidate_str, pattern):
            return True
    return False


def route(file_path: Path, csv_header_values: list[str], config: Config) -> SourceRule | None:
    """Return the first SourceRule whose path_pattern matches *file_path*, or None.

    Args:
        file_path: Absolute path to the file being classified.
        csv_header_values: Column names from the first line of the file (for CSVs).
            Currently unused for pattern matching but passed for extensibility.
        config: The loaded configuration.

    Returns:
        The first matching SourceRule, or None if no rule matches.
    """
    for rule in config.sources:
        if rule.path_pattern is None:
            continue
        if _match_pattern(file_path, rule.path_pattern):
            return rule
    return None


def _read_csv_headers(file_path: Path) -> list[str]:
    """Read the first line of a CSV file and return the column names.

    Tries common delimiters via csv.Sniffer; falls back to splitting on commas.
    Returns an empty list if the file cannot be read or has no header.
    """
    try:
        raw = file_path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        first_line = text.split("\n", 1)[0]
        try:
            dialect = csv.Sniffer().sniff(first_line, delimiters=",;\t|")
            reader = csv.reader(io.StringIO(first_line), dialect)
        except csv.Error:
            reader = csv.reader(io.StringIO(first_line))
        for row in reader:
            return [col.strip() for col in row]
    except OSError:
        pass
    return []


def discover(input_path: Path, config: Config) -> DiscoveredFiles:
    """Recursively walk *input_path* and classify every file.

    Classification rules:
    - ``.csv``  → try to route; if matched → statement, else → unrouted
    - ``.pdf``  → try to route; if matched → statement, else → candidate_doc
    - image suffixes (``.png``, ``.jpg``, ``.jpeg``, ``.tiff``, ``.bmp``) → candidate_doc
    - anything else → ignored

    Args:
        input_path: Root directory to scan (recursively).
        config: The loaded configuration.

    Returns:
        A DiscoveredFiles instance with every file classified.
    """
    result = DiscoveredFiles()

    for file_path in sorted(input_path.rglob("*")):
        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()

        if suffix == ".csv":
            headers = _read_csv_headers(file_path)
            matched_rule = route(file_path, headers, config)
            if matched_rule is not None:
                result.statements.append((file_path, matched_rule))
            else:
                result.unrouted.append(file_path)

        elif suffix == ".pdf":
            matched_rule = route(file_path, [], config)
            if matched_rule is not None:
                result.statements.append((file_path, matched_rule))
            else:
                result.candidate_docs.append(file_path)

        elif suffix in _IMAGE_SUFFIXES:
            result.candidate_docs.append(file_path)

        else:
            result.ignored.append(file_path)

    return result
