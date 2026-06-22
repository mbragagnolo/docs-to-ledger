"""Tests for docs_to_ledger.matching.match() — TDD first pass."""
from __future__ import annotations

import datetime
from decimal import Decimal

from docs_to_ledger.fingerprint import normalize_description, transaction_id
from docs_to_ledger.matching import match
from docs_to_ledger.model import DocumentFeature, MatchSettings, Transaction

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_txn(
    date: datetime.date,
    desc: str,
    debit: Decimal | None = None,
    credit: Decimal | None = None,
    account: str = "Test",
    occ: int = 0,
) -> Transaction:
    amount = debit if debit is not None else credit
    assert amount is not None, "debit or credit must be provided"
    txn_id = transaction_id(account, date, amount, normalize_description(desc))
    return Transaction(
        date=date,
        description=desc,
        debit=debit,
        credit=credit,
        account=account,
        source_file="test.csv",
        txn_id=txn_id,
        occurrence=occ,
    )


def make_doc(
    amount: Decimal,
    date: datetime.date | None = None,
    vendor: str | None = None,
    path: str = "receipt.pdf",
) -> DocumentFeature:
    return DocumentFeature(
        source_path=path,
        amount=amount,
        date=date,
        vendor=vendor,
        needs_ocr=False,
    )


D = datetime.date
TODAY = D(2024, 3, 15)
AMT = Decimal("149.90")
ZERO_TOL = MatchSettings(date_window_days=3, amount_tolerance=Decimal("0"), fuzzy_vendor=True)
ZERO_NO_FUZZY = MatchSettings(
    date_window_days=3, amount_tolerance=Decimal("0"), fuzzy_vendor=False
)


# ---------------------------------------------------------------------------
# Basic match
# ---------------------------------------------------------------------------


class TestBasicMatch:
    def test_exact_match_in_links(self) -> None:
        """1 txn + 1 doc, exact amount, same date → matched, confidence in links."""
        txn = make_txn(TODAY, "Coffee Shop", debit=AMT)
        doc = make_doc(AMT, date=TODAY, vendor="Coffee Shop")
        outcome = match([txn], [doc], ZERO_TOL)

        key = (txn.txn_id, txn.occurrence)
        assert key in outcome.links
        linked_doc, confidence = outcome.links[key]
        assert linked_doc is doc
        assert confidence > 0.0
        assert outcome.unmatched_txns == []
        assert outcome.ambiguous_docs == []
        assert outcome.unmatchable_docs == []

    def test_unmatched_transaction_no_docs(self) -> None:
        """Transaction with no document → in unmatched_txns."""
        txn = make_txn(TODAY, "No receipt", debit=AMT)
        outcome = match([txn], [], ZERO_TOL)

        assert txn in outcome.unmatched_txns
        assert outcome.links == {}
        assert outcome.ambiguous_docs == []
        assert outcome.unmatchable_docs == []

    def test_unmatched_transaction_amount_differs(self) -> None:
        """Document with wrong amount → txn unmatched, doc unmatchable."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(Decimal("200.00"), date=TODAY)
        outcome = match([txn], [doc], ZERO_TOL)

        assert txn in outcome.unmatched_txns
        assert doc in outcome.unmatchable_docs
        assert outcome.links == {}

    def test_document_no_matching_transaction_in_unmatchable(self) -> None:
        """Document with no matching transaction → unmatchable_docs."""
        doc = make_doc(AMT, date=TODAY, vendor="Vendor")
        outcome = match([], [doc], ZERO_TOL)

        assert doc in outcome.unmatchable_docs
        assert outcome.links == {}
        assert outcome.unmatched_txns == []


# ---------------------------------------------------------------------------
# Amount tolerance
# ---------------------------------------------------------------------------


class TestAmountTolerance:
    def test_zero_tolerance_tiny_diff_no_match(self) -> None:
        """Default tolerance=0: amount differs by 0.01 → no match."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT + Decimal("0.01"), date=TODAY)
        settings = ZERO_NO_FUZZY
        outcome = match([txn], [doc], settings)

        assert txn in outcome.unmatched_txns
        assert doc in outcome.unmatchable_docs

    def test_half_dollar_tolerance_matches(self) -> None:
        """Tolerance=0.50: amount within 0.50 → match."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT + Decimal("0.49"), date=TODAY)
        settings = MatchSettings(
            date_window_days=3, amount_tolerance=Decimal("0.50"), fuzzy_vendor=False
        )
        outcome = match([txn], [doc], settings)

        key = (txn.txn_id, txn.occurrence)
        assert key in outcome.links

    def test_amount_outside_tolerance_unmatchable(self) -> None:
        """Amount outside tolerance → unmatchable_docs."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT + Decimal("1.00"), date=TODAY)
        settings = MatchSettings(
            date_window_days=3, amount_tolerance=Decimal("0.50"), fuzzy_vendor=False
        )
        outcome = match([txn], [doc], settings)

        assert doc in outcome.unmatchable_docs
        assert txn in outcome.unmatched_txns

    def test_tolerance_confidence_lower_than_exact(self) -> None:
        """Match via tolerance has confidence ~0.75, exact has ~0.8."""
        txn_exact = make_txn(TODAY, "Exact", debit=Decimal("100.00"), account="A", occ=0)
        doc_exact = make_doc(Decimal("100.00"), date=TODAY, path="exact.pdf")

        txn_tol = make_txn(TODAY, "Tolerant", debit=Decimal("200.00"), account="B", occ=0)
        doc_tol = make_doc(
            Decimal("200.30"), date=TODAY + datetime.timedelta(days=1), path="tol.pdf"
        )

        settings = MatchSettings(
            date_window_days=3, amount_tolerance=Decimal("0.50"), fuzzy_vendor=False
        )
        outcome = match([txn_exact, txn_tol], [doc_exact, doc_tol], settings)

        _, conf_exact = outcome.links[(txn_exact.txn_id, txn_exact.occurrence)]
        _, conf_tol = outcome.links[(txn_tol.txn_id, txn_tol.occurrence)]
        # tolerance match should be <= exact match confidence
        assert conf_tol <= conf_exact


# ---------------------------------------------------------------------------
# Date window
# ---------------------------------------------------------------------------


class TestDateWindow:
    def test_same_date_matches(self) -> None:
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT, date=TODAY)
        outcome = match([txn], [doc], ZERO_TOL)
        assert (txn.txn_id, txn.occurrence) in outcome.links

    def test_date_exactly_at_window_matches(self) -> None:
        """Date differs by exactly date_window_days (3) → inclusive match."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT, date=TODAY + datetime.timedelta(days=3))
        settings = ZERO_NO_FUZZY
        outcome = match([txn], [doc], settings)
        assert (txn.txn_id, txn.occurrence) in outcome.links

    def test_date_one_beyond_window_no_match(self) -> None:
        """Date differs by date_window_days + 1 → no match."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT, date=TODAY + datetime.timedelta(days=4))
        settings = ZERO_NO_FUZZY
        outcome = match([txn], [doc], settings)
        assert txn in outcome.unmatched_txns
        assert doc in outcome.unmatchable_docs

    def test_date_none_unmatchable(self) -> None:
        """doc.date is None → unmatchable_docs."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc = make_doc(AMT, date=None)
        outcome = match([txn], [doc], ZERO_TOL)
        assert doc in outcome.unmatchable_docs
        assert txn in outcome.unmatched_txns


# ---------------------------------------------------------------------------
# Fuzzy vendor tie-break
# ---------------------------------------------------------------------------


class TestFuzzyVendorTieBreak:
    def test_fuzzy_picks_closer_description(self) -> None:
        """Two txns same amount+date, one description matches vendor → pick that one."""
        txn_a = make_txn(TODAY, "Starbucks Coffee", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY, "Amazon Prime", debit=AMT, account="B", occ=0)
        doc = make_doc(AMT, date=TODAY, vendor="Starbucks")

        settings = ZERO_TOL
        outcome = match([txn_a, txn_b], [doc], settings)

        # txn_a should be linked (higher fuzzy score for "Starbucks")
        assert (txn_a.txn_id, txn_a.occurrence) in outcome.links
        assert (txn_b.txn_id, txn_b.occurrence) not in outcome.links
        assert doc not in outcome.ambiguous_docs

    def test_fuzzy_identical_scores_ambiguous(self) -> None:
        """Two candidates with same fuzzy score → ambiguous_docs."""
        # Use identical descriptions so scores tie perfectly
        txn_a = make_txn(TODAY, "Store ABC", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY, "Store ABC", debit=AMT, account="B", occ=0)
        doc = make_doc(AMT, date=TODAY, vendor="Store ABC")

        settings = ZERO_TOL
        outcome = match([txn_a, txn_b], [doc], settings)

        assert doc in outcome.ambiguous_docs

    def test_fuzzy_disabled_two_candidates_ambiguous(self) -> None:
        """fuzzy_vendor=False with two candidates → ambiguous_docs."""
        txn_a = make_txn(TODAY, "Store A", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY, "Store B", debit=AMT, account="B", occ=0)
        doc = make_doc(AMT, date=TODAY, vendor="Store A")

        settings = ZERO_NO_FUZZY
        outcome = match([txn_a, txn_b], [doc], settings)

        assert doc in outcome.ambiguous_docs

    def test_fuzzy_no_vendor_two_candidates_ambiguous(self) -> None:
        """doc.vendor is None with two candidates → ambiguous_docs (no vendor to disambiguate)."""
        txn_a = make_txn(TODAY, "Store A", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY, "Store B", debit=AMT, account="B", occ=0)
        doc = make_doc(AMT, date=TODAY, vendor=None)

        settings = ZERO_TOL
        outcome = match([txn_a, txn_b], [doc], settings)

        assert doc in outcome.ambiguous_docs

    def test_fuzzy_vendor_confidence_boost(self) -> None:
        """When fuzzy vendor tie-break is used, confidence > 0.8."""
        txn_a = make_txn(TODAY, "Starbucks Coffee", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY, "Amazon Prime", debit=AMT, account="B", occ=0)
        doc = make_doc(AMT, date=TODAY, vendor="Starbucks")

        settings = ZERO_TOL
        outcome = match([txn_a, txn_b], [doc], settings)

        _, conf = outcome.links[(txn_a.txn_id, txn_a.occurrence)]
        assert conf > 0.8


# ---------------------------------------------------------------------------
# Ambiguous
# ---------------------------------------------------------------------------


class TestAmbiguous:
    def test_doc_matches_two_txns_equally_ambiguous(self) -> None:
        """Document matches two transactions equally (amount+date, no vendor) → ambiguous_docs."""
        txn_a = make_txn(TODAY, "Thing A", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY, "Thing B", debit=AMT, account="B", occ=0)
        doc = make_doc(AMT, date=TODAY, vendor=None)

        outcome = match([txn_a, txn_b], [doc], ZERO_TOL)

        assert doc in outcome.ambiguous_docs
        # Neither transaction should be linked via this doc
        assert (txn_a.txn_id, txn_a.occurrence) not in outcome.links
        assert (txn_b.txn_id, txn_b.occurrence) not in outcome.links

    def test_one_txn_two_docs_best_in_links_other_unmatchable(self) -> None:
        """One transaction matches two documents → best doc in links, other unmatchable."""
        txn = make_txn(TODAY, "Store", debit=AMT)
        doc_a = make_doc(AMT, date=TODAY, vendor="Store", path="a.pdf")
        doc_b = make_doc(AMT, date=TODAY + datetime.timedelta(days=2), vendor=None, path="b.pdf")

        # doc_a: same date → more confident; doc_b: 2-day offset → less confident
        outcome = match([txn], [doc_a, doc_b], ZERO_TOL)

        key = (txn.txn_id, txn.occurrence)
        assert key in outcome.links
        # The other doc should be unmatchable (already claimed by txn)
        total_fates = len(outcome.links) + len(outcome.unmatchable_docs)
        assert total_fates == 2  # both docs accounted for
        assert doc_b in outcome.unmatchable_docs


# ---------------------------------------------------------------------------
# Credit / debit abs amount
# ---------------------------------------------------------------------------


class TestCreditDebitAbsAmount:
    def test_credit_matches_doc_amount(self) -> None:
        """Transaction with credit=149.90 matches doc.amount=149.90."""
        txn = make_txn(TODAY, "Salary", credit=AMT)
        doc = make_doc(AMT, date=TODAY)
        outcome = match([txn], [doc], ZERO_TOL)
        assert (txn.txn_id, txn.occurrence) in outcome.links

    def test_debit_matches_doc_amount(self) -> None:
        """Transaction with debit=149.90 matches doc.amount=149.90."""
        txn = make_txn(TODAY, "Bill", debit=AMT)
        doc = make_doc(AMT, date=TODAY)
        outcome = match([txn], [doc], ZERO_TOL)
        assert (txn.txn_id, txn.occurrence) in outcome.links

    def test_credit_not_matching_wrong_amount(self) -> None:
        """Credit transaction with different amount → no match."""
        txn = make_txn(TODAY, "Payment", credit=AMT)
        doc = make_doc(Decimal("99.99"), date=TODAY)
        outcome = match([txn], [doc], ZERO_TOL)
        assert txn in outcome.unmatched_txns
        assert doc in outcome.unmatchable_docs


# ---------------------------------------------------------------------------
# One-doc-per-transaction rule
# ---------------------------------------------------------------------------


class TestOneDocPerTransaction:
    def test_two_docs_same_txn_best_wins(self) -> None:
        """Two docs matching same transaction → best doc in links, other in unmatchable_docs."""
        txn = make_txn(TODAY, "Groceries", debit=AMT)
        doc_a = make_doc(AMT, date=TODAY, vendor="Groceries", path="a.pdf")
        doc_b = make_doc(AMT, date=TODAY + datetime.timedelta(days=1), vendor=None, path="b.pdf")

        settings = ZERO_TOL
        outcome = match([txn], [doc_a, doc_b], settings)

        key = (txn.txn_id, txn.occurrence)
        assert key in outcome.links
        assert len(outcome.links) == 1
        # One doc should be in unmatchable
        assert len(outcome.unmatchable_docs) == 1
        # No unmatched txns
        assert outcome.unmatched_txns == []

    def test_two_identical_docs_one_wins_first(self) -> None:
        """Two docs with equal confidence for same txn → one (first) in links, other unmatchable."""
        txn = make_txn(TODAY, "Groceries", debit=AMT)
        doc_a = make_doc(AMT, date=TODAY, vendor=None, path="a.pdf")
        doc_b = make_doc(AMT, date=TODAY, vendor=None, path="b.pdf")

        outcome = match([txn], [doc_a, doc_b], ZERO_TOL)

        key = (txn.txn_id, txn.occurrence)
        assert key in outcome.links
        assert len(outcome.unmatchable_docs) == 1

    def test_multiple_txns_multiple_docs_each_matched(self) -> None:
        """Two transactions, each with one document → two links, no leftovers."""
        txn_a = make_txn(TODAY, "Coffee", debit=AMT, account="A", occ=0)
        txn_b = make_txn(TODAY + datetime.timedelta(days=5), "Lunch", debit=Decimal("25.00"),
                         account="B", occ=0)
        doc_a = make_doc(AMT, date=TODAY, path="coffee.pdf")
        doc_b = make_doc(
            Decimal("25.00"), date=TODAY + datetime.timedelta(days=5), path="lunch.pdf"
        )

        outcome = match([txn_a, txn_b], [doc_a, doc_b], ZERO_TOL)

        assert (txn_a.txn_id, txn_a.occurrence) in outcome.links
        assert (txn_b.txn_id, txn_b.occurrence) in outcome.links
        assert outcome.unmatched_txns == []
        assert outcome.unmatchable_docs == []
        assert outcome.ambiguous_docs == []
