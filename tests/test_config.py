"""Tests for docs_to_ledger/config.py — load_config()."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from docs_to_ledger.config import load_config
from docs_to_ledger.errors import ConfigError
from docs_to_ledger.model import ArchiveSettings, Config, Locale, MatchSettings

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadConfigValid:
    def test_loads_without_error(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert isinstance(cfg, Config)

    def test_sources_count(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert len(cfg.sources) == 1

    def test_source_account(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.sources[0].account == "SG Compte Courant"

    def test_source_statement_type(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.sources[0].statement_type == "csv"

    def test_source_path_pattern(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.sources[0].path_pattern == "statements/**/*.csv"

    def test_source_locale_date_format(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.sources[0].locale.date_format == "dd/mm/yyyy"

    def test_source_locale_decimal_separator(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.sources[0].locale.decimal_separator == "comma"

    def test_source_locale_thousands_separator(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.sources[0].locale.thousands_separator == "space"

    def test_source_column_map(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        cm = cfg.sources[0].column_map
        assert cm == {
            "date": "Date", "description": "Libelle", "debit": "Debit", "credit": "Credit"
        }

    def test_matching_date_window(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.matching.date_window_days == 3

    def test_matching_amount_tolerance(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.matching.amount_tolerance == Decimal("0")

    def test_matching_fuzzy_vendor(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.matching.fuzzy_vendor is True

    def test_archive_root(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.archive.root == "archive"

    def test_archive_layout(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.archive.layout == "year/month"

    def test_default_format(self) -> None:
        cfg = load_config(FIXTURES / "docs-to-ledger.yaml")
        assert cfg.format == "xlsx"

    def test_accepts_string_path(self) -> None:
        cfg = load_config(str(FIXTURES / "docs-to-ledger.yaml"))
        assert isinstance(cfg, Config)


class TestLoadConfigErrors:
    def test_missing_file_raises_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_missing_sources_raises_config_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("matching:\n  date_window_days: 3\n")
        with pytest.raises(ConfigError, match="sources"):
            load_config(bad_yaml)

    def test_empty_sources_list_raises_config_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("sources: []\n")
        with pytest.raises(ConfigError, match="sources"):
            load_config(bad_yaml)

    def test_source_missing_account_raises_config_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "sources:\n  - statement_type: csv\n    path_pattern: '**/*.csv'\n"
        )
        with pytest.raises(ConfigError, match="account"):
            load_config(bad_yaml)

    def test_source_missing_statement_type_raises_config_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(
            "sources:\n  - account: 'MyBank'\n    path_pattern: '**/*.csv'\n"
        )
        with pytest.raises(ConfigError, match="statement_type"):
            load_config(bad_yaml)

    def test_invalid_yaml_raises_config_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":\n  - invalid: [yaml\n")
        with pytest.raises(ConfigError):
            load_config(bad_yaml)

    def test_non_dict_yaml_raises_config_error(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("- just a list\n")
        with pytest.raises(ConfigError):
            load_config(bad_yaml)


class TestLoadConfigDefaults:
    def test_minimal_config_uses_default_matching(self, tmp_path: Path) -> None:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
        )
        cfg = load_config(minimal)
        assert cfg.matching == MatchSettings()

    def test_minimal_config_uses_default_archive(self, tmp_path: Path) -> None:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
        )
        cfg = load_config(minimal)
        assert cfg.archive == ArchiveSettings()

    def test_minimal_config_uses_default_format(self, tmp_path: Path) -> None:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
        )
        cfg = load_config(minimal)
        assert cfg.format == "xlsx"

    def test_minimal_config_source_uses_default_locale(self, tmp_path: Path) -> None:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
        )
        cfg = load_config(minimal)
        assert cfg.sources[0].locale == Locale()

    def test_minimal_config_source_column_map_empty(self, tmp_path: Path) -> None:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
        )
        cfg = load_config(minimal)
        assert cfg.sources[0].column_map == {}

    def test_output_dir_none_by_default(self, tmp_path: Path) -> None:
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
        )
        cfg = load_config(minimal)
        assert cfg.output_dir is None

    def test_output_dir_loaded_when_present(self, tmp_path: Path) -> None:
        cfg_yaml = tmp_path / "cfg.yaml"
        cfg_yaml.write_text(
            "sources:\n  - account: 'Bank'\n    statement_type: csv\n"
            "output_dir: '/some/path'\n"
        )
        cfg = load_config(cfg_yaml)
        assert cfg.output_dir == "/some/path"
