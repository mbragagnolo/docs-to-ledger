from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Literal


class MatchStatus(str, Enum):
    matched = "matched"
    unmatched = "unmatched"
    ambiguous = "ambiguous"


@dataclass
class Transaction:
    date: datetime.date
    description: str
    debit: Decimal | None
    credit: Decimal | None
    account: str
    source_file: str
    txn_id: str
    occurrence: int


@dataclass
class DocumentFeature:
    source_path: str
    amount: Decimal
    date: datetime.date | None
    vendor: str | None
    needs_ocr: bool


@dataclass
class Locale:
    date_format: str = "dd/mm/yyyy"
    decimal_separator: Literal["comma", "dot"] = "comma"
    thousands_separator: Literal["space", "dot", "comma", "none"] = "space"


@dataclass
class SourceRule:
    account: str
    statement_type: Literal["csv", "pdf"]
    locale: Locale = field(default_factory=Locale)
    path_pattern: str | None = None
    column_map: dict[str, str] = field(default_factory=dict)
    pdf_profile: str | None = None


@dataclass
class MatchSettings:
    date_window_days: int = 3
    amount_tolerance: Decimal = field(default_factory=lambda: Decimal("0"))
    fuzzy_vendor: bool = True


@dataclass
class ArchiveSettings:
    root: str = "archive"
    layout: Literal["year/month", "flat"] = "year/month"


@dataclass
class Config:
    sources: list[SourceRule]
    matching: MatchSettings = field(default_factory=MatchSettings)
    archive: ArchiveSettings = field(default_factory=ArchiveSettings)
    output_dir: str | None = None
    format: Literal["xlsx", "ods"] = "xlsx"


@dataclass
class MatchOutcome:
    links: dict[tuple[str, int], tuple[DocumentFeature, float]] = field(default_factory=dict)
    unmatched_txns: list[Transaction] = field(default_factory=list)
    ambiguous_docs: list[DocumentFeature] = field(default_factory=list)
    unmatchable_docs: list[DocumentFeature] = field(default_factory=list)


@dataclass
class RunReport:
    rows_added: int = 0
    rows_updated: int = 0
    docs_matched: int = 0
    docs_copied: int = 0
    review_items: int = 0
    unrouted: int = 0
    parse_failures: int = 0
