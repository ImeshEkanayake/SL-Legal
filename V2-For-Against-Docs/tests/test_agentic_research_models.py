from __future__ import annotations

import pytest
from pydantic import ValidationError

from sl_legal_rag.models import (
    AgentResearchPlan,
    AgentToolTrace,
    AuthorityPackExpansionPlan,
    AuthorityExpansionCandidate,
    ClarificationNeed,
    MatterMemory,
)


def trace(
    trace_id: str,
    tool_name: str,
    source_boundary: str,
    *,
    status: str = "completed",
    result_count: int | None = 1,
) -> dict[str, object]:
    return {
        "trace_id": trace_id,
        "tool_name": tool_name,
        "purpose": f"{tool_name} purpose",
        "source_boundary": source_boundary,
        "input_summary": {"case_id": "case_001"},
        "result_count": result_count,
        "status": status,
        "selected_outputs": [{"id": "selected_001"}] if result_count else [],
        "reviewer_note": f"{tool_name} reviewer note",
    }


def candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": "cand_001",
        "title": "Supreme Court authority on trademark confusion",
        "authority_type": "Supreme Court case",
        "citation_or_identifier": "SC Appeal No. 1/2020",
        "originating_tool_trace_id": "trace_expand",
        "source_hint": "Stage-1 authority expansion",
        "status": "candidate_unverified",
        "verification_status": "requires_lawyer_review",
        "reviewer_note": "Candidate only; not citable until sealed into a pack.",
    }
    payload.update(overrides)
    return payload


def test_phase_16_agent_research_plan_accepts_db_first_tool_route() -> None:
    plan = AgentResearchPlan.model_validate(
        {
            "plan_id": "plan_001",
            "matter_id": "matter_001",
            "requested_output": "lawyer_review_pack",
            "tool_traces": [
                trace("trace_intake", "case_intake_structurer", "user_input"),
                trace("trace_search", "search_database", "database", result_count=25),
                trace("trace_expand", "expand_authorities", "candidate_authorities", result_count=8),
                trace("trace_official", "official_source_check", "official_source", result_count=3),
                trace("trace_answer", "answer_from_pack", "sealed_pack", result_count=1),
                trace("trace_review", "lawyer_review_pack", "generated_draft", result_count=1),
            ],
            "authority_candidates": [candidate()],
            "reviewer_summary": "DB-first route with candidate authority expansion and official-source checks.",
        }
    )

    assert plan.schema_version == "agent_research_plan.v1"
    assert plan.tool_traces[1].tool_name == "search_database"
    assert plan.authority_candidates[0].citable is False


def test_phase_16_tool_trace_rejects_wrong_source_boundary() -> None:
    with pytest.raises(ValidationError, match="answer_from_pack cannot use source boundary database"):
        AgentToolTrace.model_validate(trace("trace_answer", "answer_from_pack", "database"))


def test_phase_16_completed_tool_trace_requires_result_count() -> None:
    with pytest.raises(ValidationError, match="completed or empty tool traces require result_count"):
        AgentToolTrace.model_validate(
            trace("trace_search", "search_database", "database", status="completed", result_count=None)
        )


def test_phase_16_failed_tool_trace_requires_error_metadata() -> None:
    payload = trace("trace_search", "search_database", "database", status="failed", result_count=0)

    with pytest.raises(ValidationError, match="failed tool traces require metadata.error"):
        AgentToolTrace.model_validate(payload)


def test_phase_16_official_source_check_requires_prior_authority_expansion() -> None:
    with pytest.raises(ValidationError, match="official_source_check requires a prior expand_authorities trace"):
        AgentResearchPlan.model_validate(
            {
                "plan_id": "plan_001",
                "matter_id": "matter_001",
                "tool_traces": [
                    trace("trace_search", "search_database", "database"),
                    trace("trace_official", "official_source_check", "official_source"),
                ],
                "reviewer_summary": "Invalid route.",
            }
        )


def test_phase_16_clarification_needs_require_ask_clarification_trace() -> None:
    clarification = {
        "clarification_id": "clarify_001",
        "category": "client_position",
        "question": "Are we acting for the claimant or respondent?",
        "reason": "Client position changes the for/against stance analysis.",
        "blocks_preliminary_opinion": True,
    }

    with pytest.raises(ValidationError, match="clarification needs require an ask_clarification trace"):
        AgentResearchPlan.model_validate(
            {
                "plan_id": "plan_001",
                "matter_id": "matter_001",
                "tool_traces": [trace("trace_search", "search_database", "database")],
                "clarification_needs": [clarification],
                "reviewer_summary": "Invalid route.",
            }
        )

    accepted = AgentResearchPlan.model_validate(
        {
            "plan_id": "plan_001",
            "matter_id": "matter_001",
            "tool_traces": [
                trace("trace_search", "search_database", "database"),
                trace("trace_clarify", "ask_clarification", "user_input", status="requires_clarification", result_count=None),
            ],
            "clarification_needs": [clarification],
            "reviewer_summary": "Clarification blocks stronger opinion until answered.",
        }
    )

    assert accepted.clarification_needs[0].blocks_preliminary_opinion is True


def test_phase_16_authority_candidates_are_not_citable_until_promoted() -> None:
    raw_candidate = AuthorityExpansionCandidate.model_validate(candidate())

    assert raw_candidate.citable is False

    with pytest.raises(ValidationError, match="promoted authority candidates require promoted_pack_item_ids"):
        AuthorityExpansionCandidate.model_validate(candidate(status="promoted_to_sealed_pack"))

    with pytest.raises(ValidationError, match="unpromoted authority candidates must not carry promoted pack item ids"):
        AuthorityExpansionCandidate.model_validate(candidate(promoted_pack_item_ids=["pack_item_001"]))


def test_phase_16_matter_memory_requires_trace_for_candidates_and_sealed_pack_for_promotion() -> None:
    expand_trace = AgentToolTrace.model_validate(trace("trace_expand", "expand_authorities", "candidate_authorities"))
    promoted_candidate = AuthorityExpansionCandidate.model_validate(
        candidate(status="promoted_to_sealed_pack", promoted_pack_item_ids=["pack_item_001"])
    )

    with pytest.raises(ValidationError, match="promoted authority candidates require at least one sealed_pack_id"):
        MatterMemory.model_validate(
            {
                "matter_id": "matter_001",
                "candidate_authorities": [promoted_candidate],
                "tool_traces": [expand_trace],
            }
        )

    memory = MatterMemory.model_validate(
        {
            "matter_id": "matter_001",
            "sealed_pack_ids": ["pack_001"],
            "client_facts": ["Client owns the mark."],
            "adverse_material": ["Confusion evidence is not yet complete."],
            "missing_evidence_tasks": ["Obtain NIPO registration certificate."],
            "clarification_needs": [
                ClarificationNeed.model_validate(
                    {
                        "clarification_id": "clarify_001",
                        "category": "registration_number",
                        "question": "What is the trademark registration number?",
                        "reason": "The number is needed to verify ownership and current status.",
                    }
                )
            ],
            "candidate_authorities": [promoted_candidate],
            "tool_traces": [expand_trace],
        }
    )

    assert memory.promoted_pack_item_ids == {"pack_item_001"}
    assert memory.unresolved_blocking_clarifications[0].category == "registration_number"


def test_phase_21_authority_pack_expansion_plan_is_non_citable_and_official_only() -> None:
    plan = AuthorityPackExpansionPlan.model_validate(
        {
            "plan_id": "authplan_001",
            "case_id": "case_001",
            "draft_id": "draft_001",
            "review_item_id": "review_001",
            "parent_pack_id": "pack_001",
            "candidate_ids": ["cand_001"],
            "expansion_requests": [
                {
                    "query": "SC Appeal No. 1/2020 Supreme Court trademark confusion",
                    "query_class": "case_law_lookup",
                    "filters": {"require_official": True, "authority_levels": [1, 3]},
                    "purpose": "authority_candidate_pack_expansion",
                }
            ],
        }
    )

    assert plan.schema_version == "authority_pack_expansion_plan.v1"
    assert plan.citable is False
    assert plan.expansion_requests[0].filters.require_official is True

    with pytest.raises(ValidationError, match="authority expansion plans must not be citable"):
        AuthorityPackExpansionPlan.model_validate(
            {
                "plan_id": "authplan_001",
                "case_id": "case_001",
                "draft_id": "draft_001",
                "review_item_id": "review_001",
                "parent_pack_id": "pack_001",
                "candidate_ids": ["cand_001"],
                "expansion_requests": [
                    {
                        "query": "SC Appeal No. 1/2020 Supreme Court trademark confusion",
                        "filters": {"require_official": True},
                        "purpose": "authority_candidate_pack_expansion",
                    }
                ],
                "citable": True,
            }
        )


def test_phase_22_executed_authority_expansion_plan_requires_matching_child_packs() -> None:
    payload = {
        "plan_id": "authplan_001",
        "case_id": "case_001",
        "draft_id": "draft_001",
        "review_item_id": "review_001",
        "parent_pack_id": "pack_001",
        "status": "executed",
        "candidate_ids": ["cand_001"],
        "expansion_requests": [
            {
                "query": "SC Appeal No. 1/2020 Supreme Court trademark confusion",
                "query_class": "case_law_lookup",
                "filters": {"require_official": True, "authority_levels": [1, 3]},
                "purpose": "authority_candidate_pack_expansion",
            }
        ],
        "executed_pack_ids": ["pack_child_001"],
        "execution_records": [
            {
                "request_index": 0,
                "child_pack_id": "pack_child_001",
                "child_pack_hash": "hash_001",
                "item_count": 3,
                "executed_by_user_id": "user_001",
                "executed_at": "2026-05-29T13:31:00",
                "request_query_sha256": "a" * 64,
            }
        ],
    }

    plan = AuthorityPackExpansionPlan.model_validate(payload)

    assert plan.status == "executed"
    assert plan.executed_pack_ids == ["pack_child_001"]

    with pytest.raises(ValidationError, match="executed_pack_ids must match execution record child pack ids"):
        AuthorityPackExpansionPlan.model_validate({**payload, "executed_pack_ids": ["pack_other"]})
