# backend/app/retrieval/verifier.py
import re
from typing import Any, Dict, List, Tuple


def normalize_whitespace(text: str) -> str:
    """Collapses newlines, tabs, and multiple spaces for robust substring alignment."""
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_substring_spans(
    claims: List[Dict[str, Any]],
    context_sources: Dict[str, str]
) -> Tuple[List[Dict[str, Any]], List[str], float]:
    """
    Deterministically verifies that verbatim quotes in claimed sources exist byte-for-byte
    (or normalized) in the actual retrieved context (email body or attachment text).

    Args:
        claims: List of claim dictionaries with sources.
        context_sources: Dict mapping identifier (email_id or filename) to raw text context.

    Returns:
        (verified_claims, failed_claim_texts, faithfulness_score)
    """
    verified_claims = []
    failed_claims = []
    total_quotes = 0
    passed_quotes = 0

    # Build combined normalized context
    norm_contexts = {k: normalize_whitespace(v) for k, v in context_sources.items()}
    all_combined_context = " ".join(norm_contexts.values())

    for claim in claims:
        claim_text = claim.get("claim_text", "")
        sources = claim.get("sources", [])
        claim_valid = True
        updated_sources = []

        for src in sources:
            quote = src.get("verbatim_quote", "")
            if not quote:
                src["substring_verified"] = False
                updated_sources.append(src)
                continue

            total_quotes += 1
            norm_quote = normalize_whitespace(quote)

            # Check if quote exists in its specific target source or any retrieved source
            source_id = src.get("email_id") or src.get("attachment_filename")
            is_matched = False

            if source_id and source_id in norm_contexts:
                if norm_quote in norm_contexts[source_id]:
                    is_matched = True

            if not is_matched and norm_quote in all_combined_context:
                is_matched = True

            src["substring_verified"] = is_matched
            if is_matched:
                passed_quotes += 1
                updated_sources.append(src)
            else:
                claim_valid = False

        if claim_valid and len(updated_sources) > 0:
            claim["sources"] = updated_sources
            verified_claims.append(claim)
        else:
            failed_claims.append(claim_text)

    faithfulness = (passed_quotes / total_quotes) if total_quotes > 0 else 1.0
    return verified_claims, failed_claims, round(faithfulness, 2)
