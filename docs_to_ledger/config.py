"""Config loading: parse docs-to-ledger YAML into a Config dataclass."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from docs_to_ledger.errors import ConfigError
from docs_to_ledger.model import (
    ArchiveSettings,
    Config,
    Locale,
    MatchSettings,
    SourceRule,
)


def _parse_locale(data: dict[str, Any]) -> Locale:
    dec_sep_raw: Any = data.get("decimal_separator", "comma")
    dec_sep_str = str(dec_sep_raw) if dec_sep_raw is not None else "comma"
    if dec_sep_str not in ("comma", "dot"):
        raise ConfigError(
            f"locale.decimal_separator must be 'comma' or 'dot', got {dec_sep_str!r}"
        )
    dec_sep = cast("Literal['comma', 'dot']", dec_sep_str)

    thou_sep_raw: Any = data.get("thousands_separator", "space")
    thou_sep_str = str(thou_sep_raw) if thou_sep_raw is not None else "space"
    if thou_sep_str not in ("space", "dot", "comma", "none"):
        raise ConfigError(
            f"locale.thousands_separator must be 'space', 'dot', 'comma', or 'none',"
            f" got {thou_sep_str!r}"
        )
    thou_sep = cast("Literal['space', 'dot', 'comma', 'none']", thou_sep_str)

    date_format_raw: Any = data.get("date_format", "dd/mm/yyyy")
    date_format = str(date_format_raw) if date_format_raw is not None else "dd/mm/yyyy"

    return Locale(
        date_format=date_format,
        decimal_separator=dec_sep,
        thousands_separator=thou_sep,
    )


def _parse_source_rule(data: Any, index: int) -> SourceRule:
    if not isinstance(data, dict):
        raise ConfigError(f"sources[{index}] must be a mapping, got {type(data).__name__}")

    account = data.get("account")
    if not account:
        raise ConfigError(f"sources[{index}] is missing required field 'account'")

    statement_type_raw: Any = data.get("statement_type")
    if not statement_type_raw:
        raise ConfigError(f"sources[{index}] is missing required field 'statement_type'")
    statement_type_str = str(statement_type_raw)
    if statement_type_str not in ("csv", "pdf"):
        raise ConfigError(
            f"sources[{index}].statement_type must be 'csv' or 'pdf', got {statement_type_str!r}"
        )
    statement_type = cast("Literal['csv', 'pdf']", statement_type_str)

    locale_data = data.get("locale", {})
    locale = _parse_locale(locale_data) if isinstance(locale_data, dict) else Locale()

    column_map: dict[str, str] = {}
    raw_map = data.get("column_map", {})
    if isinstance(raw_map, dict):
        column_map = {str(k): str(v) for k, v in raw_map.items()}

    path_pattern: str | None = data.get("path_pattern")
    if path_pattern is not None:
        path_pattern = str(path_pattern)

    pdf_profile: str | None = data.get("pdf_profile")
    if pdf_profile is not None:
        pdf_profile = str(pdf_profile)

    return SourceRule(
        account=str(account),
        statement_type=statement_type,
        locale=locale,
        path_pattern=path_pattern,
        column_map=column_map,
        pdf_profile=pdf_profile,
    )


def _parse_matching(data: dict[str, Any]) -> MatchSettings:
    tolerance_raw = data.get("amount_tolerance", 0)
    return MatchSettings(
        date_window_days=int(data.get("date_window_days", 3)),
        amount_tolerance=Decimal(str(tolerance_raw)),
        fuzzy_vendor=bool(data.get("fuzzy_vendor", True)),
    )


def _parse_archive(data: dict[str, Any]) -> ArchiveSettings:
    layout_raw: Any = data.get("layout", "year/month")
    layout_str = str(layout_raw) if layout_raw is not None else "year/month"
    if layout_str not in ("year/month", "flat"):
        raise ConfigError(f"archive.layout must be 'year/month' or 'flat', got {layout_str!r}")
    layout = cast("Literal['year/month', 'flat']", layout_str)
    return ArchiveSettings(
        root=str(data.get("root", "archive")),
        layout=layout,
    )


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config file into a Config object.

    Raises:
        ConfigError: if the file is missing, unreadable, or contains invalid/missing fields.
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")

    try:
        raw_text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {p}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(
            f"Config file must contain a YAML mapping at the top level, got {type(data).__name__}"
        )

    raw_sources: Any = data.get("sources")
    if not isinstance(raw_sources, list) or len(raw_sources) == 0:
        raise ConfigError(
            "Config is missing required field 'sources' (must be a non-empty list)"
        )

    sources = [_parse_source_rule(item, i) for i, item in enumerate(raw_sources)]

    raw_matching = data.get("matching", {})
    matching = _parse_matching(raw_matching) if isinstance(raw_matching, dict) else MatchSettings()

    raw_archive = data.get("archive", {})
    archive = _parse_archive(raw_archive) if isinstance(raw_archive, dict) else ArchiveSettings()

    output_dir_raw: Any = data.get("output_dir")
    output_dir: str | None = str(output_dir_raw) if output_dir_raw is not None else None

    fmt_raw: Any = data.get("format", "xlsx")
    fmt_str = str(fmt_raw) if fmt_raw is not None else "xlsx"
    if fmt_str not in ("xlsx", "ods"):
        raise ConfigError(f"'format' must be 'xlsx' or 'ods', got {fmt_str!r}")
    fmt = cast("Literal['xlsx', 'ods']", fmt_str)

    return Config(
        sources=sources,
        matching=matching,
        archive=archive,
        output_dir=output_dir,
        format=fmt,
    )
