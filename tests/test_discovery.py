"""Tests for docs_to_ledger/discovery.py — route() and discover()."""
from __future__ import annotations

from pathlib import Path

from docs_to_ledger.config import load_config
from docs_to_ledger.discovery import DiscoveredFiles, discover, route
from docs_to_ledger.model import Config, SourceRule

FIXTURES = Path(__file__).parent / "fixtures"


def _make_config(*rules: SourceRule) -> Config:
    return Config(sources=list(rules))


def _make_rule(pattern: str, account: str = "TestBank") -> SourceRule:
    return SourceRule(account=account, statement_type="csv", path_pattern=pattern)


class TestRoute:
    def test_returns_none_when_no_rules(self, tmp_path: Path) -> None:
        f = tmp_path / "file.csv"
        f.touch()
        cfg = _make_config()
        assert route(f, [], cfg) is None

    def test_returns_none_when_no_pattern_matches(self, tmp_path: Path) -> None:
        f = tmp_path / "other" / "file.csv"
        f.parent.mkdir()
        f.touch()
        rule = _make_rule("statements/**/*.csv")
        cfg = _make_config(rule)
        assert route(f, [], cfg) is None

    def test_returns_matching_rule(self, tmp_path: Path) -> None:
        f = tmp_path / "statements" / "2026" / "june.csv"
        f.parent.mkdir(parents=True)
        f.touch()
        rule = _make_rule("statements/**/*.csv")
        cfg = _make_config(rule)
        result = route(f, [], cfg)
        assert result is rule

    def test_returns_first_matching_rule(self, tmp_path: Path) -> None:
        f = tmp_path / "statements" / "data.csv"
        f.parent.mkdir()
        f.touch()
        rule1 = _make_rule("statements/*.csv", account="First")
        rule2 = _make_rule("statements/*.csv", account="Second")
        cfg = _make_config(rule1, rule2)
        result = route(f, [], cfg)
        assert result is rule1

    def test_rule_without_pattern_does_not_match(self, tmp_path: Path) -> None:
        f = tmp_path / "anything.csv"
        f.touch()
        rule = SourceRule(account="NoPattern", statement_type="csv", path_pattern=None)
        cfg = _make_config(rule)
        assert route(f, [], cfg) is None

    def test_matches_pdf_rule(self, tmp_path: Path) -> None:
        f = tmp_path / "invoices" / "inv001.pdf"
        f.parent.mkdir()
        f.touch()
        rule = SourceRule(
            account="PDFBank", statement_type="pdf", path_pattern="invoices/*.pdf"
        )
        cfg = _make_config(rule)
        result = route(f, [], cfg)
        assert result is rule

    def test_absolute_path_matches_relative_pattern(self, tmp_path: Path) -> None:
        """Path pattern is relative; matching works regardless of absolute prefix."""
        deep = tmp_path / "a" / "b" / "statements" / "file.csv"
        deep.parent.mkdir(parents=True)
        deep.touch()
        rule = _make_rule("statements/*.csv")
        cfg = _make_config(rule)
        result = route(deep, [], cfg)
        assert result is rule


class TestDiscover:
    def _fixture_config(self) -> Config:
        return load_config(FIXTURES / "docs-to-ledger.yaml")

    def test_csv_matching_pattern_in_statements(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "statements" / "2026" / "june.csv"
        csv_file.parent.mkdir(parents=True)
        csv_file.write_text("Date;Libelle;Debit;Credit\n15/06/2026;TEST;-10;\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert any(p == csv_file for p, _ in result.statements)

    def test_csv_matching_pattern_has_correct_rule(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "statements" / "2026" / "june.csv"
        csv_file.parent.mkdir(parents=True)
        csv_file.write_text("Date;Libelle;Debit;Credit\n15/06/2026;TEST;-10;\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        matched_rules = [rule for p, rule in result.statements if p == csv_file]
        assert len(matched_rules) == 1
        assert matched_rules[0].account == "SG Compte Courant"

    def test_csv_non_matching_path_in_unrouted(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "downloads" / "misc.csv"
        csv_file.parent.mkdir(parents=True)
        csv_file.write_text("col1,col2\nval1,val2\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert csv_file in result.unrouted

    def test_pdf_with_no_matching_rule_in_candidate_docs(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "receipts" / "invoice.pdf"
        pdf_file.parent.mkdir(parents=True)
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert pdf_file in result.candidate_docs

    def test_png_in_candidate_docs(self, tmp_path: Path) -> None:
        img_file = tmp_path / "receipt.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert img_file in result.candidate_docs

    def test_jpg_in_candidate_docs(self, tmp_path: Path) -> None:
        img_file = tmp_path / "receipt.jpg"
        img_file.write_bytes(b"\xff\xd8\xff")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert img_file in result.candidate_docs

    def test_jpeg_in_candidate_docs(self, tmp_path: Path) -> None:
        img_file = tmp_path / "scan.jpeg"
        img_file.write_bytes(b"\xff\xd8\xff")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert img_file in result.candidate_docs

    def test_tiff_in_candidate_docs(self, tmp_path: Path) -> None:
        img_file = tmp_path / "scan.tiff"
        img_file.write_bytes(b"II*\x00")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert img_file in result.candidate_docs

    def test_bmp_in_candidate_docs(self, tmp_path: Path) -> None:
        img_file = tmp_path / "scan.bmp"
        img_file.write_bytes(b"BM")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert img_file in result.candidate_docs

    def test_txt_in_ignored(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("just notes\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert txt_file in result.ignored

    def test_yaml_in_ignored(self, tmp_path: Path) -> None:
        yml_file = tmp_path / "config.yaml"
        yml_file.write_text("key: value\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        assert yml_file in result.ignored

    def test_recursive_walk_finds_nested_file(self, tmp_path: Path) -> None:
        deep_csv = tmp_path / "statements" / "2026" / "06" / "sg.csv"
        deep_csv.parent.mkdir(parents=True)
        deep_csv.write_text("Date;Libelle;Debit;Credit\n15/06/2026;TEST;-10;\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        all_files = (
            [p for p, _ in result.statements]
            + result.candidate_docs
            + result.unrouted
            + result.ignored
        )
        assert deep_csv in all_files

    def test_pdf_matching_rule_in_statements(self, tmp_path: Path) -> None:
        pdf_file = tmp_path / "statements" / "2026" / "bank.pdf"
        pdf_file.parent.mkdir(parents=True)
        pdf_file.write_bytes(b"%PDF-1.4\n%%EOF\n")
        rule = SourceRule(
            account="PDFBank",
            statement_type="pdf",
            path_pattern="statements/**/*.pdf",
        )
        cfg = Config(sources=[rule])
        result = discover(tmp_path, cfg)
        assert any(p == pdf_file for p, _ in result.statements)

    def test_returns_discovered_files_type(self, tmp_path: Path) -> None:
        cfg = _make_config()
        result = discover(tmp_path, cfg)
        assert isinstance(result, DiscoveredFiles)

    def test_empty_directory_returns_empty_results(self, tmp_path: Path) -> None:
        cfg = _make_config()
        result = discover(tmp_path, cfg)
        assert result.statements == []
        assert result.candidate_docs == []
        assert result.unrouted == []
        assert result.ignored == []

    def test_csv_header_used_for_routing(self, tmp_path: Path) -> None:
        """route() receives the CSV header values (first line columns)."""
        csv_file = tmp_path / "statements" / "data.csv"
        csv_file.parent.mkdir(parents=True)
        # Write a CSV with a distinctive header
        csv_file.write_text("Date;Libelle;Debit;Credit\n15/06/2026;TEST;-10;\n")
        cfg = self._fixture_config()
        result = discover(tmp_path, cfg)
        # The file should be classified (routed or unrouted), not ignored
        classified = [p for p, _ in result.statements] + result.unrouted
        assert csv_file in classified
