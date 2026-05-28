from __future__ import annotations

import pytest
from pydantic import ValidationError

from sl_legal_rag.models import (
    ClaimEvidenceAssessmentRequest,
    EvidenceStance,
    citation_role_for_evidence_stance,
    evidence_stance_for_citation_role,
)


def assessment_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "claim_text": "The employer refused to bargain with a qualifying trade union.",
        "pack_id": "pack_1",
        "pack_item_id": "pack_1_item_001",
        "stance": "supports_claim",
        "rationale": "The source states the employer must bargain with the qualifying union.",
        "confidence_score": 0.87,
        "risk_level": "medium",
        "source_quote": "No employer shall refuse to bargain.",
        "page_start": 1,
        "page_end": 2,
    }
    payload.update(overrides)
    return payload


def test_evidence_stance_maps_to_citation_roles():
    assert citation_role_for_evidence_stance(EvidenceStance.SUPPORTS_CLAIM) == "support"
    assert citation_role_for_evidence_stance("contradicts_claim") == "adverse"
    assert evidence_stance_for_citation_role("mixed") == EvidenceStance.MIXED
    assert evidence_stance_for_citation_role("context") == EvidenceStance.CONTEXT


def test_assessment_requires_claim_text_when_claim_id_is_missing():
    with pytest.raises(ValidationError, match="claim_text is required"):
        ClaimEvidenceAssessmentRequest.model_validate(assessment_payload(claim_text=None))


def test_assessment_allows_existing_claim_id_without_claim_text():
    assessment = ClaimEvidenceAssessmentRequest.model_validate(
        assessment_payload(claim_id="claim_1", claim_text=None)
    )

    assert assessment.claim_id == "claim_1"
    assert assessment.claim_text is None
    assert assessment.citation_role == "support"


def test_mixed_assessment_requires_rationale_and_valid_page_range():
    with pytest.raises(ValidationError, match="rationale"):
        ClaimEvidenceAssessmentRequest.model_validate(
            assessment_payload(stance="mixed", rationale=" ")
        )
    with pytest.raises(ValidationError, match="page_end"):
        ClaimEvidenceAssessmentRequest.model_validate(
            assessment_payload(stance="mixed", page_start=4, page_end=2)
        )


def test_one_pack_item_can_take_different_stances_for_different_claims():
    support = ClaimEvidenceAssessmentRequest.model_validate(
        assessment_payload(
            claim_text="The union can rely on the duty to bargain.",
            stance="supports_claim",
        )
    )
    adverse = ClaimEvidenceAssessmentRequest.model_validate(
        assessment_payload(
            claim_text="The employer can argue the union was not qualified.",
            stance="contradicts_claim",
            rationale="The same authority helps only if the qualification threshold is met.",
            risk_level="high",
        )
    )

    assert support.pack_item_id == adverse.pack_item_id
    assert support.citation_role == "support"
    assert adverse.citation_role == "adverse"
