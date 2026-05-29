from __future__ import annotations

from sl_legal_rag.agentic_research import build_agentic_research_bundle, identify_clarification_needs
from sl_legal_rag.models import LegalResearchPack, StrategyDraftResponse


def research_pack() -> LegalResearchPack:
    return LegalResearchPack.model_validate(
        {
            "pack_id": "pack_agentic_001",
            "query": "trademark infringement confusion",
            "query_class": "case_law_lookup",
            "filters": {},
            "retrieval_config": {"max_tokens": 12000},
            "items": [
                {
                    "pack_item_id": "pack_agentic_001_item_001",
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "title": "Code of Intellectual Property Act",
                    "document_type": "Act",
                    "source_id": "ACTS",
                    "authority_level": 2,
                    "citation": "Code of Intellectual Property Act",
                    "text": "Trademark infringement and confusion provisions.",
                    "fused_score": 0.9,
                    "selection_reason": "exact citation candidate",
                }
            ],
        }
    )


def strategy_response() -> StrategyDraftResponse:
    return StrategyDraftResponse.model_validate(
        {
            "pack_id": "pack_agentic_001",
            "answer": "The trademark claim is arguable on a preliminary basis. [pack_agentic_001_item_001]",
            "claims": [
                {
                    "claim": "The trademark claim is arguable on a preliminary basis.",
                    "pack_item_ids": ["pack_agentic_001_item_001"],
                    "confidence": "needs_lawyer_review",
                }
            ],
            "counterarguments": [
                {
                    "counterargument": "The respondent may argue the mark is descriptive.",
                    "supporting_pack_item_ids": ["pack_agentic_001_item_001"],
                    "response": "The client needs registration and market confusion evidence.",
                    "response_pack_item_ids": ["pack_agentic_001_item_001"],
                    "risk_level": "medium",
                }
            ],
            "missing_authorities": ["Supreme Court case-law on trademark confusion still needs retrieval."],
            "warnings": ["Lawyer review required."],
        }
    )


def test_phase_17_agentic_bundle_records_pack_bound_route_and_candidates() -> None:
    pack = research_pack()
    draft = strategy_response()

    bundle = build_agentic_research_bundle(
        case_facts=(
            "We act for the right-holder in a trademark dispute in 2024. "
            "The respondent used a similar label in Colombo."
        ),
        research_pack=pack,
        requested_output="lawyer_review_pack",
        strategy_response=draft,
        matter_id="case_001",
    )

    metadata = bundle.metadata()
    trace_names = [trace.tool_name for trace in bundle.plan.tool_traces]

    assert metadata["agentic_research_plan"]["schema_version"] == "agent_research_plan.v1"
    assert metadata["matter_memory"]["schema_version"] == "matter_memory.v1"
    assert trace_names[:3] == ["case_intake_structurer", "search_database", "expand_authorities"]
    assert "official_source_check" in trace_names
    assert bundle.plan.authority_candidates[0].citable is False
    assert bundle.plan.authority_candidates[0].originating_tool_trace_id == "trace_expand_authorities"
    assert bundle.matter_memory.sealed_pack_ids == [pack.pack_id]
    assert "descriptive" in bundle.matter_memory.adverse_material[0]
    assert bundle.matter_memory.missing_evidence_tasks[0].startswith("Supreme Court")


def test_phase_17_clarification_policy_blocks_weak_ip_opinion_without_registration() -> None:
    needs = identify_clarification_needs(
        case_facts="A trademark judgment excerpt says IP Act coverage may apply.",
        requested_output="lawyer_review_pack",
    )

    categories = {need.category for need in needs}
    blocking = {need.category for need in needs if need.blocks_preliminary_opinion}

    assert {"client_position", "dates", "registration_number", "case_number"}.issubset(categories)
    assert {"client_position", "dates", "registration_number", "case_number"}.issubset(blocking)

