from __future__ import annotations

import pytest

from sl_legal_rag.models import LegalResearchPack, StrategyDraftResponse
from sl_legal_rag.product_policy import (
    LegalRiskLevel,
    PolicyStatus,
    SourceReliabilityTier,
    authority_label,
    evaluate_strategy_output_policy,
    evaluate_text_policy,
    require_policy_allowance,
    source_reliability_tier,
    source_reliability_warnings,
)
from sl_legal_rag.strategy import generate_strategy_draft


class FakeJsonClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, **_kwargs):
        return self.payload


def pack_with_source(*, source_id: str = "PARL_ACTS", authority_level: int = 2) -> LegalResearchPack:
    return LegalResearchPack.model_validate(
        {
            "pack_id": "pack_policy",
            "query": "trade union bargaining",
            "query_class": "general_research",
            "filters": {},
            "retrieval_config": {"max_tokens": 12000},
            "items": [
                {
                    "pack_item_id": "pack_policy_item_001",
                    "chunk_id": "chunk_policy_001",
                    "document_id": "doc_policy_001",
                    "title": "Industrial Disputes Act",
                    "document_type": "Act",
                    "source_id": source_id,
                    "authority_level": authority_level,
                    "citation": "Industrial Disputes Act",
                    "text": "An employer shall not refuse to bargain with a qualifying trade union.",
                    "fused_score": 1.0,
                    "selection_reason": "policy test fixture",
                }
            ],
        }
    )


def test_phase_0_policy_blocks_fabricated_authority_requests():
    evaluation = evaluate_text_policy("Please fabricate a case citation to support this submission.")

    assert evaluation.status == PolicyStatus.BLOCK
    assert evaluation.risk_level == LegalRiskLevel.CRITICAL
    assert evaluation.violations[0].code == "fabricate_authority"
    with pytest.raises(ValueError, match="fabricate authority"):
        require_policy_allowance(evaluation)


def test_phase_0_policy_requires_review_for_legal_strategy_requests():
    evaluation = evaluate_text_policy("Prepare a court strategy report from cited authorities.")

    assert evaluation.status == PolicyStatus.REVIEW_REQUIRED
    assert evaluation.risk_level == LegalRiskLevel.HIGH
    assert evaluation.review.lawyer_review_required
    assert evaluation.review.reviewer_role == "qualified_lawyer"


def test_phase_0_source_reliability_and_authority_labels_are_deterministic():
    assert source_reliability_tier("PARL_ACTS") == SourceReliabilityTier.OFFICIAL
    assert source_reliability_tier("LANKALAW_LIBRARY") == SourceReliabilityTier.LICENSED_PUBLISHER
    assert source_reliability_tier("unknown_blog") == SourceReliabilityTier.UNVERIFIED
    assert "Acts" in authority_label(2)
    assert authority_label(999) == "Unclassified authority"


def test_phase_0_policy_warns_when_pack_has_only_unverified_or_secondary_sources():
    warnings = source_reliability_warnings(pack_with_source(source_id="unknown_blog", authority_level=6))

    assert any("unverified" in warning.lower() for warning in warnings)
    assert any("secondary" in warning.lower() for warning in warnings)


def test_phase_0_strategy_policy_blocks_final_advice_even_with_valid_pack_citation():
    pack = pack_with_source()
    response = StrategyDraftResponse.model_validate(
        {
            "pack_id": pack.pack_id,
            "answer": "This is final legal advice: the client is guaranteed to win. [pack_policy_item_001]",
            "claims": [
                {
                    "claim": "The client is guaranteed to win.",
                    "pack_item_ids": ["pack_policy_item_001"],
                    "confidence": "needs_lawyer_review",
                }
            ],
        }
    )

    evaluation = evaluate_strategy_output_policy(
        response=response,
        pack=pack,
        requested_output="strategy_report",
    )

    assert evaluation.status == PolicyStatus.BLOCK
    assert {violation.code for violation in evaluation.violations} >= {"final_legal_advice", "guaranteed_outcome"}


def test_phase_0_strategy_policy_surfaces_missing_source_warnings():
    pack = pack_with_source()
    pack.missing_source_summary = "Older Court of Appeal authorities are not complete."
    response = StrategyDraftResponse.model_validate(
        {
            "pack_id": pack.pack_id,
            "answer": "The cited Act supports a lawyer-review argument. [pack_policy_item_001]",
            "claims": [
                {
                    "claim": "The cited Act supports a lawyer-review argument.",
                    "pack_item_ids": ["pack_policy_item_001"],
                }
            ],
            "missing_authorities": [],
        }
    )

    evaluation = evaluate_strategy_output_policy(
        response=response,
        pack=pack,
        requested_output="strategy_report",
    )

    assert evaluation.status == PolicyStatus.REVIEW_REQUIRED
    assert any("missing-source" in warning for warning in evaluation.warnings)


def test_phase_0_generation_rejects_policy_blocked_strategy_output():
    pack = pack_with_source()
    client = FakeJsonClient(
        {
            "pack_id": pack.pack_id,
            "answer": "This is final legal advice and the client is guaranteed to win. [pack_policy_item_001]",
            "claims": [
                {
                    "claim": "The client is guaranteed to win.",
                    "pack_item_ids": ["pack_policy_item_001"],
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="Product policy blocked output|unsafe final-advice wording"):
        generate_strategy_draft(
            case_facts="The employer refused to bargain.",
            pack=pack,
            client=client,
            requested_output="strategy_report",
        )
