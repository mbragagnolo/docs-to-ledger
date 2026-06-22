"""Document-to-transaction matching engine.

Confidence scale
----------------
1.0  = exact amount, same date, vendor match (fuzzy >= 60)
0.8  = exact amount, date within window (no vendor info or vendor didn't help)
0.75 = amount within tolerance (> 0), date within window
Ambiguous docs: not placed in links at all
Threshold for "matched": any score > 0 placed in links is considered matched
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from rapidfuzz import fuzz

from docs_to_ledger.model import (
    DocumentFeature,
    MatchOutcome,
    MatchSettings,
    Transaction,
)

# Minimum fuzzy score required to use vendor as a tie-breaker.
_FUZZY_THRESHOLD = 60


def _txn_amount(txn: Transaction) -> Decimal:
    """Return the transaction amount (debit takes priority over credit)."""
    if txn.debit is not None:
        return txn.debit
    assert txn.credit is not None, "Transaction must have debit or credit"
    return txn.credit


def _amount_matches(txn_amt: Decimal, doc_amt: Decimal, tolerance: Decimal) -> bool:
    return abs(txn_amt - doc_amt) <= tolerance


def _date_matches(txn: Transaction, doc: DocumentFeature, window: int) -> bool:
    if doc.date is None:
        return False
    return abs((txn.date - doc.date).days) <= window


def _base_confidence(settings: MatchSettings) -> float:
    """Compute base confidence (before fuzzy boost) for a candidate pair.

    Returns 0.75 when amount_tolerance > 0 (inexact amount match), else 0.8.
    """
    if settings.amount_tolerance > Decimal("0"):
        return 0.75
    return 0.8


def _fuzzy_score(vendor: str, description: str) -> float:
    return fuzz.token_sort_ratio(vendor, description)


def match(
    transactions: list[Transaction],
    documents: list[DocumentFeature],
    settings: MatchSettings,
) -> MatchOutcome:
    """Pure function — no disk I/O, no file copying.

    Matching rules
    --------------
    1. Amount match: abs(txn_amount - doc.amount) <= settings.amount_tolerance
       where txn_amount = txn.debit if not None else txn.credit (always positive).

    2. Date match: abs(txn.date - doc.date) <= date_window_days (inclusive).
       If doc.date is None: date match fails → unmatchable_docs.

    3. For pairs that pass amount+date:
       - Exactly one candidate → matched (high confidence).
       - Multiple candidates → fuzzy vendor tie-break if settings.fuzzy_vendor and doc.vendor:
           * score = rapidfuzz.fuzz.token_sort_ratio(doc.vendor, txn.description)
           * top score >= 60 and uniquely best → matched with fuzzy boost
           * otherwise → ambiguous_docs.

    4. One-doc-per-transaction: if multiple docs match one transaction, highest-confidence
       doc is linked; extras go to unmatchable_docs.

    5. Transactions with no matched doc → unmatched_txns.

    Confidence
    ----------
    - 0.8  base: exact tolerance (amount_tolerance == 0), date within window
    - 0.75 base: amount within tolerance > 0, date within window
    - fuzzy boost: +0.2 * (fuzzy_score / 100) when vendor tie-break resolves the match,
      giving up to 1.0 for a perfect vendor match on a same-date exact-amount transaction
    """
    outcome = MatchOutcome()

    # Docs that can never be matched due to missing date (detected up front)
    matchable_docs: list[DocumentFeature] = []
    for doc in documents:
        if doc.date is None:
            outcome.unmatchable_docs.append(doc)
        else:
            matchable_docs.append(doc)

    # Build candidate matrix: for each doc, which transactions could match?
    # Structure: doc_index → list of (txn, base_confidence)
    doc_candidates: dict[int, list[tuple[Transaction, float]]] = {
        i: [] for i in range(len(matchable_docs))
    }

    for doc_idx, doc in enumerate(matchable_docs):
        txn_amt_ref = doc.amount
        for txn in transactions:
            txn_amt = _txn_amount(txn)
            if not _amount_matches(txn_amt, txn_amt_ref, settings.amount_tolerance):
                continue
            if not _date_matches(txn, doc, settings.date_window_days):
                continue
            conf = _base_confidence(settings)
            doc_candidates[doc_idx].append((txn, conf))

    # Resolve each document to a confirmed (txn, confidence) pair or place in ambiguous.
    # We collect (doc, txn, confidence) proposals then apply one-doc-per-txn rule.
    proposals: list[tuple[DocumentFeature, Transaction, float]] = []

    for doc_idx, doc in enumerate(matchable_docs):
        candidates = doc_candidates[doc_idx]

        if not candidates:
            outcome.unmatchable_docs.append(doc)
            continue

        if len(candidates) == 1:
            txn, conf = candidates[0]
            proposals.append((doc, txn, conf))
            continue

        # Multiple candidates — try fuzzy vendor tie-break
        if settings.fuzzy_vendor and doc.vendor:
            scored: list[tuple[Transaction, float, float]] = []  # (txn, base_conf, fuzzy)
            for txn, base_conf in candidates:
                fscore = _fuzzy_score(doc.vendor, txn.description)
                scored.append((txn, base_conf, fscore))

            best_fscore = max(s[2] for s in scored)
            if best_fscore >= _FUZZY_THRESHOLD:
                best_candidates = [s for s in scored if s[2] == best_fscore]
                if len(best_candidates) == 1:
                    txn, base_conf, fscore = best_candidates[0]
                    boosted_conf = base_conf + 0.2 * (fscore / 100.0)
                    proposals.append((doc, txn, boosted_conf))
                    continue

        # Could not disambiguate
        outcome.ambiguous_docs.append(doc)

    # Apply one-doc-per-transaction rule: each txn key can only be linked to one doc.
    # Group proposals by (txn_id, occurrence).
    txn_key_proposals: dict[
        tuple[str, int], list[tuple[DocumentFeature, float]]
    ] = defaultdict(list)
    for doc, txn, conf in proposals:
        key = (txn.txn_id, txn.occurrence)
        txn_key_proposals[key].append((doc, conf))

    # Linked txn keys
    linked_txn_keys: set[tuple[str, int]] = set()

    for key, doc_conf_list in txn_key_proposals.items():
        # Sort by descending confidence, then by source_path for determinism
        doc_conf_list.sort(key=lambda dc: (-dc[1], dc[0].source_path))
        winner_doc, winner_conf = doc_conf_list[0]
        outcome.links[key] = (winner_doc, winner_conf)
        linked_txn_keys.add(key)
        # All other docs that tried to claim this txn go to unmatchable
        for extra_doc, _ in doc_conf_list[1:]:
            outcome.unmatchable_docs.append(extra_doc)

    # Transactions with no link → unmatched_txns
    for txn in transactions:
        key = (txn.txn_id, txn.occurrence)
        if key not in linked_txn_keys:
            outcome.unmatched_txns.append(txn)

    return outcome
