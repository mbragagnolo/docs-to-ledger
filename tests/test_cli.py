"""Tests for the CLI entry point (cli.main)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from docs_to_ledger.cli import main
from docs_to_ledger.errors import ConfigError, OutputWriteError
from docs_to_ledger.model import RunReport
from docs_to_ledger.runner import RunArgs

_CONFIG = """\
sources:
  - account: "Test Account"
    statement_type: csv
    path_pattern: "statements/*.csv"
    column_map:
      date: "Date"
      description: "Libelle"
      debit: "Debit"
      credit: "Credit"
"""

_CSV = "Date;Libelle;Debit;Credit\n15/06/2026;SUPER U;-149,90;\n"


@pytest.fixture()
def tree(tmp_path: Path) -> dict[str, Path]:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    stmts = tmp_path / "input" / "statements"
    stmts.mkdir(parents=True)
    (stmts / "bank.csv").write_text(_CSV, encoding="utf-8")

    return {
        "config_path": config_path,
        "input_path": tmp_path / "input",
        "output_dir": tmp_path / "output",
    }


# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------


def test_defaults_passed_to_runner(tmp_path: Path) -> None:
    """CLI defaults: format=xlsx, dry_run=False, output_dir=None."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    with patch("docs_to_ledger.cli.run") as mock_run:
        mock_run.return_value = RunReport()
        main([str(tmp_path), "--config", str(config_path)])

    called_args: RunArgs = mock_run.call_args[0][0]
    assert called_args.format == "xlsx"
    assert called_args.dry_run is False
    assert called_args.output_dir is None


def test_dry_run_flag_passed(tmp_path: Path) -> None:
    """--dry-run sets dry_run=True on RunArgs."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    with patch("docs_to_ledger.cli.run") as mock_run:
        mock_run.return_value = RunReport()
        main([str(tmp_path), "--config", str(config_path), "--dry-run"])

    called_args: RunArgs = mock_run.call_args[0][0]
    assert called_args.dry_run is True


def test_format_ods_passed(tmp_path: Path) -> None:
    """--format ods sets format='ods' on RunArgs."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    with patch("docs_to_ledger.cli.run") as mock_run:
        mock_run.return_value = RunReport()
        main([str(tmp_path), "--config", str(config_path), "--format", "ods"])

    called_args: RunArgs = mock_run.call_args[0][0]
    assert called_args.format == "ods"


def test_output_dir_passed(tmp_path: Path) -> None:
    """--output-dir is forwarded as a Path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")
    out = tmp_path / "my_output"

    with patch("docs_to_ledger.cli.run") as mock_run:
        mock_run.return_value = RunReport()
        main([str(tmp_path), "--config", str(config_path), "--output-dir", str(out)])

    called_args: RunArgs = mock_run.call_args[0][0]
    assert called_args.output_dir == out


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_success_returns_0(tree: dict[str, Path]) -> None:
    """Successful run exits 0."""
    with patch("docs_to_ledger.runner.extract_features", return_value=None):
        rc = main([
            str(tree["input_path"]),
            "--config", str(tree["config_path"]),
            "--output-dir", str(tree["output_dir"]),
        ])
    assert rc == 0


def test_missing_config_returns_1(tmp_path: Path) -> None:
    """Missing config file exits 1 with a message to stderr."""
    rc = main([str(tmp_path), "--config", str(tmp_path / "no_such.yaml")])
    assert rc == 1


def test_config_error_returns_1(tmp_path: Path) -> None:
    """ConfigError from runner exits 1."""
    with patch("docs_to_ledger.cli.run", side_effect=ConfigError("bad config")):
        rc = main([str(tmp_path), "--config", str(tmp_path / "x.yaml")])
    assert rc == 1


def test_output_write_error_returns_1(tmp_path: Path) -> None:
    """OutputWriteError from runner exits 1."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_CONFIG, encoding="utf-8")

    with patch("docs_to_ledger.cli.run", side_effect=OutputWriteError("locked")):
        rc = main([str(tmp_path), "--config", str(config_path)])
    assert rc == 1


def test_dry_run_success_returns_0(tree: dict[str, Path]) -> None:
    """--dry-run also exits 0."""
    with patch("docs_to_ledger.runner.extract_features", return_value=None):
        rc = main([
            str(tree["input_path"]),
            "--config", str(tree["config_path"]),
            "--output-dir", str(tree["output_dir"]),
            "--dry-run",
        ])
    assert rc == 0
