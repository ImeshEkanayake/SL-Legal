from __future__ import annotations

import pytest
from pydantic import ValidationError

from sl_legal_rag.models import AuthorityVerification, FactLawMapping, PreliminaryLegalOpinion, ReasoningPackOutput


def reasoning_pack_output() -> dict[str, object]:
    return {
        "schema_version": "reasoning_pack.v1",
        "output_type": "lawyer_review_pack",
        "authority_verifications": [
            {
                "authority_id": "AUTH_001",
                "title": "Industrial Disputes Act",
                "authority_type": "Act",
                "citation": "Industrial Disputes Act s 1",
                "pack_item_ids": ["pack_reasoning_item_001"],
                "verification_status": "requires_lawyer_review",
            }
        ],
        "issue_matrix": [
            {
                "issue_id": "ISSUE_001",
                "issue": "Whether refusal to bargain is prohibited.",
                "legal_area": "Labour law",
                "elements": [
                    {
                        "element_id": "ELEMENT_001",
                        "element": "Qualifying trade union status.",
                        "pack_item_ids": ["pack_reasoning_item_001"],
                        "missing_evidence": ["Union registration certificate."],
                    }
                ],
                "facts_supporting": ["The employer refused to bargain."],
                "facts_against": ["Union qualification is not yet proved."],
                "missing_evidence": ["Worker representation evidence."],
                "confidence": 0.55,
            }
        ],
        "fact_to_law_mappings": [
            {
                "issue_id": "ISSUE_001",
                "fact": "The employer refused to bargain.",
                "legal_question": "Whether the refusal engages the statutory duty.",
                "supporting_reasoning": "The pack suggests refusal to bargain may be prohibited if qualification is proven.",
                "risk": "The qualification element requires further evidence.",
                "missing_documents": ["Union registration certificate."],
                "pack_item_ids": ["pack_reasoning_item_001"],
            }
        ],
        "for_against_brief": [
            {
                "issue_id": "ISSUE_001",
                "issue": "Whether refusal to bargain is prohibited.",
                "legal_basis": [
                    {
                        "authority": "Industrial Disputes Act",
                        "proposition": "Refusal to bargain may be prohibited where statutory conditions are met.",
                        "pack_item_ids": ["pack_reasoning_item_001"],
                    }
                ],
                "facts_relied_on": ["The employer refused to bargain."],
                "client_argument": "The refusal supports the client's position if qualification is established.",
                "opposing_argument": "The opposing party may argue the union was not qualifying.",
                "rebuttal": "The client should collect registration and representation evidence.",
                "missing_evidence": ["Union registration certificate."],
                "strength": "medium",
                "confidence": 0.55,
            }
        ],
        "missing_evidence_checklist": ["Union registration certificate.", "Current Act verification."],
        "preliminary_legal_opinion": {
            "matter": "Trade union bargaining matter.",
            "instructions": "Assess the refusal to bargain from the current pack.",
            "important_qualification": "This is a preliminary lawyer-review draft requiring verification before reliance.",
            "assumed_facts": ["The employer refused to bargain."],
            "documents_reviewed": ["Industrial Disputes Act extract in the pack."],
            "issues": ["Whether statutory refusal-to-bargain requirements are met."],
            "applicable_law": ["Industrial Disputes Act s 1, subject to lawyer verification."],
            "analysis": "On a preliminary basis, lawyer verification is required for current force, amendments, and qualification evidence.",
            "preliminary_opinion": "The preliminary view is that the argument may be available, subject to lawyer verification and missing evidence.",
            "risks": ["Union qualification evidence is incomplete."],
            "recommended_next_steps": ["Verify the Act and collect union qualification documents."],
            "conclusion": "The preliminary conclusion remains subject to lawyer verification and further evidence.",
        },
        "lawyer_review_pack": {
            "one_page_case_summary": "Employer refusal to bargain requires review against statutory elements.",
            "issue_matrix_ids": ["ISSUE_001"],
            "authority_ids": ["AUTH_001"],
            "missing_documents": ["Union registration certificate."],
            "questions_for_client": ["When was the union registered?"],
            "questions_for_lawyer": ["Is the cited section current and amended?"],
        },
        "lawyer_verification_required": True,
    }


def test_phase_4_reasoning_pack_model_accepts_balanced_lawyer_review_pack():
    pack = ReasoningPackOutput.model_validate(reasoning_pack_output())

    assert pack.schema_version == "reasoning_pack.v1"
    assert pack.lawyer_verification_required is True
    assert pack.all_pack_item_ids() == {"pack_reasoning_item_001"}
    assert pack.for_against_brief[0].opposing_argument
    assert pack.missing_evidence_checklist


def test_phase_4_verified_authority_requires_official_and_amendment_checks():
    with pytest.raises(ValidationError, match="official source and amendment checks"):
        AuthorityVerification.model_validate(
            {
                "authority_id": "AUTH_001",
                "title": "Industrial Disputes Act",
                "authority_type": "Act",
                "citation": "Industrial Disputes Act s 1",
                "pack_item_ids": ["pack_reasoning_item_001"],
                "verification_status": "verified",
                "official_source_checked": True,
                "amendment_checked": False,
            }
        )


def test_phase_4_verified_fact_to_law_mapping_requires_pack_citation():
    with pytest.raises(ValidationError, match="verified fact-to-law mappings require"):
        FactLawMapping.model_validate(
            {
                "issue_id": "ISSUE_001",
                "fact": "The employer refused to bargain.",
                "legal_question": "Whether refusal engages the Act.",
                "supporting_reasoning": "This legal proposition must be grounded.",
                "risk": "Ungrounded citation risk.",
                "pack_item_ids": [],
                "verification_status": "verified",
                "lawyer_verification_required": True,
            }
        )


def test_phase_4_preliminary_opinion_rejects_final_advice_language():
    with pytest.raises(ValidationError, match="unsafe final-advice wording"):
        PreliminaryLegalOpinion.model_validate(
            {
                "matter": "Trade union bargaining matter.",
                "instructions": "Assess current pack.",
                "important_qualification": "This is a preliminary lawyer verification draft.",
                "assumed_facts": ["The employer refused to bargain."],
                "documents_reviewed": ["Industrial Disputes Act extract."],
                "issues": ["Whether refusal to bargain is prohibited."],
                "applicable_law": ["Industrial Disputes Act s 1."],
                "analysis": "The client has a strong case.",
                "preliminary_opinion": "The preliminary view requires lawyer verification.",
                "risks": ["Qualification evidence is incomplete."],
                "recommended_next_steps": ["Verify authority and collect documents."],
                "conclusion": "Preliminary lawyer verification remains required.",
                "lawyer_verification_required": True,
            }
        )


def test_phase_4_reasoning_pack_rejects_unknown_issue_references():
    payload = reasoning_pack_output()
    payload["fact_to_law_mappings"][0]["issue_id"] = "ISSUE_404"  # type: ignore[index]

    with pytest.raises(ValidationError, match="fact-to-law mappings reference unknown issues"):
        ReasoningPackOutput.model_validate(payload)
