from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .models import (
    AgentResearchPlan,
    AgentToolTrace,
    AuthorityPackExpansionPlan,
    AuthorityExpansionCandidate,
    ClarificationNeed,
    LegalResearchPack,
    MatterMemory,
    QueryClass,
    ReasoningPackOutput,
    ResearchPackExpansionRequest,
    StrategyDraftResponse,
)
from .research_pack import research_pack_hash


DATE_SIGNAL_RE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE)
CLIENT_POSITION_RE = re.compile(
    r"\b(?:we act for|acting for|client is|our client|claimant|plaintiff|petitioner|appellant|respondent|defendant|accused|right[- ]holder|employer|employee|union)\b",
    re.IGNORECASE,
)
PARTY_SIGNAL_RE = re.compile(r"\b(?:v\.| vs | versus |appellant|respondent|plaintiff|defendant|petitioner|company|limited|pvt|ltd)\b", re.IGNORECASE)
REGISTRATION_SIGNAL_RE = re.compile(r"\b(?:registration|reg\.?\s*no\.?|trademark\s+no\.?|mark\s+no\.?)\b", re.IGNORECASE)
CASE_NUMBER_SIGNAL_RE = re.compile(r"\b(?:sc|ca|hc|dc|mc|lt)\s*(?:appeal|application|case|writ)?\s*no\.?\b", re.IGNORECASE)
AUTHORITY_TASK_RE = re.compile(
    r"\b(?:act|section|supreme court|court of appeal|gazette|case[- ]law|authority|amendment|current[- ]treatment|nipo|statutory|regulation|ordinance)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AgenticResearchBundle:
    plan: AgentResearchPlan
    matter_memory: MatterMemory

    def metadata(self) -> dict[str, Any]:
        return {
            "agentic_research_plan": self.plan.model_dump(mode="json"),
            "matter_memory": self.matter_memory.model_dump(mode="json"),
        }


def build_agentic_research_bundle(
    *,
    case_facts: str,
    research_pack: LegalResearchPack,
    requested_output: str,
    strategy_response: StrategyDraftResponse | None = None,
    matter_id: str | None = None,
) -> AgenticResearchBundle:
    """Build an auditable, metadata-safe agentic research wrapper.

    This function does not execute retrieval, official-source web checks, or LLM
    work. It records the routed workflow around work that already happened so a
    reviewer can see what was pack-bound, what remains only a candidate, and
    where clarification is blocking stronger conclusions.
    """

    resolved_matter_id = matter_id or _stable_id("matter", research_pack.pack_id, case_facts)
    plan_id = _stable_id("plan", resolved_matter_id, research_pack.pack_id, requested_output)
    clarification_needs = identify_clarification_needs(case_facts=case_facts, requested_output=requested_output)
    authority_candidates = build_authority_candidates(strategy_response=strategy_response)
    tool_traces = build_tool_traces(
        case_facts=case_facts,
        research_pack=research_pack,
        requested_output=requested_output,
        strategy_response=strategy_response,
        clarification_count=len(clarification_needs),
        authority_candidate_count=len(authority_candidates),
    )
    plan = AgentResearchPlan.model_validate(
        {
            "plan_id": plan_id,
            "matter_id": resolved_matter_id,
            "requested_output": requested_output if requested_output in _REASONING_OUTPUTS else "strategy_report",
            "tool_traces": tool_traces,
            "clarification_needs": clarification_needs,
            "authority_candidates": authority_candidates,
            "reviewer_summary": _reviewer_summary(
                research_pack=research_pack,
                strategy_response=strategy_response,
                clarification_count=len(clarification_needs),
                authority_candidate_count=len(authority_candidates),
            ),
        }
    )
    memory = MatterMemory.model_validate(
        {
            "matter_id": resolved_matter_id,
            "case_id": research_pack.items[0].metadata.get("case_id") if research_pack.items else None,
            "client_position": infer_client_position(case_facts),
            "selected_authority_ids": _selected_authority_ids(strategy_response.reasoning_pack if strategy_response else None),
            "sealed_pack_ids": [research_pack.pack_id],
            "candidate_authorities": authority_candidates,
            "client_facts": _fact_snippets(case_facts),
            "adverse_material": _adverse_material(strategy_response),
            "missing_evidence_tasks": _missing_evidence_tasks(strategy_response),
            "clarification_needs": clarification_needs,
            "tool_traces": tool_traces,
            "review_state": {
                "lawyer_review_required": True,
                "authority_candidates_are_citable": False,
                "source_boundary": "sealed_pack",
            },
        }
    )
    return AgenticResearchBundle(plan=plan, matter_memory=memory)


def identify_clarification_needs(*, case_facts: str, requested_output: str) -> list[ClarificationNeed]:
    text = " ".join(case_facts.split())
    needs: list[ClarificationNeed] = []
    if not CLIENT_POSITION_RE.search(text):
        needs.append(
            ClarificationNeed(
                clarification_id=_stable_id("clarify", "client_position", text),
                category="client_position",
                question="Are we acting for the claimant/applicant side or the respondent/defence side?",
                reason="The client position controls which facts and authorities are supportive or adverse.",
                blocks_preliminary_opinion=requested_output in _REASONING_OUTPUTS,
            )
        )
    if not PARTY_SIGNAL_RE.search(text):
        needs.append(
            ClarificationNeed(
                clarification_id=_stable_id("clarify", "parties", text),
                category="parties",
                question="Who are the parties, and what are their legal roles?",
                reason="Party identity is needed to map facts, standing, and adverse arguments.",
                blocks_preliminary_opinion=False,
            )
        )
    if not DATE_SIGNAL_RE.search(text):
        needs.append(
            ClarificationNeed(
                clarification_id=_stable_id("clarify", "dates", text),
                category="dates",
                question="What are the material dates for the dispute and the relevant documents?",
                reason="Dates affect limitation, current-law checks, amendments, and procedural posture.",
                blocks_preliminary_opinion=requested_output in _REASONING_OUTPUTS,
            )
        )
    if "trademark" in text.lower() and not REGISTRATION_SIGNAL_RE.search(text):
        needs.append(
            ClarificationNeed(
                clarification_id=_stable_id("clarify", "registration_number", text),
                category="registration_number",
                question="What is the trademark application or registration number?",
                reason="Registration details are needed before a stronger IP opinion can be prepared.",
                blocks_preliminary_opinion=True,
            )
        )
    if "judgment" in text.lower() and not CASE_NUMBER_SIGNAL_RE.search(text):
        needs.append(
            ClarificationNeed(
                clarification_id=_stable_id("clarify", "case_number", text),
                category="case_number",
                question="What is the court case number or neutral citation for the judgment?",
                reason="Case number or report citation is needed to verify the authority precisely.",
                blocks_preliminary_opinion=True,
            )
        )
    return needs


def build_authority_candidates(*, strategy_response: StrategyDraftResponse | None) -> list[AuthorityExpansionCandidate]:
    if strategy_response is None:
        return []
    raw_candidates: list[str] = []
    raw_candidates.extend(strategy_response.missing_authorities)
    if strategy_response.reasoning_pack is not None:
        raw_candidates.extend(
            item for item in strategy_response.reasoning_pack.missing_evidence_checklist if AUTHORITY_TASK_RE.search(item)
        )
    candidates: list[AuthorityExpansionCandidate] = []
    seen: set[str] = set()
    for item in raw_candidates:
        normalized = " ".join(str(item).split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            AuthorityExpansionCandidate(
                candidate_id=_stable_id("authcand", normalized),
                title=_candidate_title(normalized),
                authority_type=_candidate_type(normalized),
                citation_or_identifier=normalized[:240],
                originating_tool_trace_id="trace_expand_authorities",
                source_hint="Missing-authority or missing-evidence task from the pack-bounded draft.",
                status="candidate_unverified",
                verification_status="requires_lawyer_review",
                reviewer_note="Candidate only; retrieve, anchor, verify, and seal before citing as law.",
            )
        )
    return candidates


def build_authority_pack_expansion_plan(
    *,
    case_id: str,
    draft_id: str,
    parent_pack_id: str,
    review_item_id: str,
    matter_memory: MatterMemory | dict[str, Any],
) -> AuthorityPackExpansionPlan | None:
    memory = matter_memory if isinstance(matter_memory, MatterMemory) else MatterMemory.model_validate(matter_memory)
    candidates = [candidate for candidate in memory.candidate_authorities if not candidate.citable]
    if not candidates:
        return None

    return AuthorityPackExpansionPlan.model_validate(
        {
            "plan_id": _stable_id(
                "authplan",
                case_id,
                draft_id,
                parent_pack_id,
                review_item_id,
                ",".join(candidate.candidate_id for candidate in candidates),
            ),
            "case_id": case_id,
            "draft_id": draft_id,
            "review_item_id": review_item_id,
            "parent_pack_id": parent_pack_id,
            "candidate_ids": [candidate.candidate_id for candidate in candidates],
            "expansion_requests": [
                ResearchPackExpansionRequest(
                    query=_authority_expansion_query(candidate),
                    query_class=_authority_expansion_query_class(candidate),
                    filters=_authority_expansion_filters(candidate),
                    max_pack_items=12,
                    max_pack_tokens=18000,
                    case_id=case_id,
                    purpose="authority_candidate_pack_expansion",
                )
                for candidate in candidates
            ],
            "citable": False,
        }
    )


def build_tool_traces(
    *,
    case_facts: str,
    research_pack: LegalResearchPack,
    requested_output: str,
    strategy_response: StrategyDraftResponse | None,
    clarification_count: int,
    authority_candidate_count: int,
) -> list[AgentToolTrace]:
    traces: list[AgentToolTrace] = [
        AgentToolTrace(
            trace_id="trace_case_intake",
            tool_name="case_intake_structurer",
            purpose="Structure supplied matter facts and identify clarification needs.",
            source_boundary="user_input",
            input_summary={"case_facts_char_count": len(case_facts), "requested_output": requested_output},
            result_count=1,
            status="completed",
            selected_outputs=[{"clarification_need_count": clarification_count}],
            reviewer_note="Client-supplied facts only; no hidden facts or external law used.",
        ),
        AgentToolTrace(
            trace_id="trace_search_database",
            tool_name="search_database",
            purpose="Use the sealed database research pack as the source-bound retrieval result.",
            source_boundary="database",
            input_summary={
                "pack_id": research_pack.pack_id,
                "pack_hash": research_pack_hash(research_pack),
                "query": research_pack.query,
                "query_class": str(research_pack.query_class),
            },
            result_count=len(research_pack.items),
            status="completed" if research_pack.items else "empty",
            selected_outputs=[{"pack_id": research_pack.pack_id, "pack_item_count": len(research_pack.items)}],
            reviewer_note="Database retrieval is the first authority source; reasoning must stay pack-bound.",
        ),
        AgentToolTrace(
            trace_id="trace_expand_authorities",
            tool_name="expand_authorities",
            purpose="Convert missing authority tasks into non-citable candidate authorities for later retrieval.",
            source_boundary="candidate_authorities",
            input_summary={"missing_authority_count": len(strategy_response.missing_authorities) if strategy_response else 0},
            result_count=authority_candidate_count,
            status="completed" if authority_candidate_count else "empty",
            selected_outputs=[{"authority_candidate_count": authority_candidate_count}],
            reviewer_note="Authority expansion outputs candidates only; they are not legal citations until promoted into a sealed pack.",
        ),
    ]
    if authority_candidate_count:
        traces.append(
            AgentToolTrace(
                trace_id="trace_official_source_check",
                tool_name="official_source_check",
                purpose="Plan official-source verification for candidate authorities and current-law gaps.",
                source_boundary="official_source",
                input_summary={"authority_candidate_count": authority_candidate_count},
                status="planned",
                reviewer_note="Official-source verification has not executed in this phase.",
            )
        )
    if clarification_count:
        traces.append(
            AgentToolTrace(
                trace_id="trace_ask_clarification",
                tool_name="ask_clarification",
                purpose="Ask material clarification questions before a stronger legal opinion.",
                source_boundary="user_input",
                input_summary={"clarification_need_count": clarification_count},
                status="requires_clarification",
                reviewer_note="Blocking questions must be resolved or carried as missing evidence.",
            )
        )
    traces.append(
        AgentToolTrace(
            trace_id="trace_answer_from_pack",
            tool_name="answer_from_pack",
            purpose="Draft only from the sealed pack and validated reasoning output.",
            source_boundary="sealed_pack",
            input_summary={"pack_id": research_pack.pack_id, "requested_output": requested_output},
            result_count=1 if strategy_response is not None else None,
            status="completed" if strategy_response is not None else "planned",
            selected_outputs=[{"claim_count": len(strategy_response.claims)}] if strategy_response is not None else [],
            reviewer_note="Any legal proposition in the answer must cite sealed pack item IDs.",
        )
    )
    traces.append(
        AgentToolTrace(
            trace_id="trace_lawyer_review_pack",
            tool_name="lawyer_review_pack",
            purpose="Prepare the reviewer-facing reasoning pack metadata.",
            source_boundary="generated_draft",
            input_summary={"reasoning_pack_present": strategy_response.reasoning_pack is not None if strategy_response else False},
            result_count=1 if strategy_response and strategy_response.reasoning_pack is not None else None,
            status="completed" if strategy_response and strategy_response.reasoning_pack is not None else "planned",
            selected_outputs=[{"output_type": strategy_response.reasoning_pack.output_type}] if strategy_response and strategy_response.reasoning_pack else [],
            reviewer_note="Lawyer review remains required before reliance.",
        )
    )
    return traces


def infer_client_position(case_facts: str) -> str | None:
    lowered = case_facts.lower()
    if "we act for" in lowered:
        return case_facts[lowered.index("we act for") :].split(".")[0][:240].strip()
    if "our client" in lowered:
        return "our client"
    for label in ("claimant", "plaintiff", "petitioner", "appellant", "respondent", "defendant", "right-holder", "union"):
        if label in lowered:
            return label
    return None


def _selected_authority_ids(reasoning_pack: ReasoningPackOutput | None) -> list[str]:
    if reasoning_pack is None:
        return []
    return [item.authority_id for item in reasoning_pack.authority_verifications]


def _fact_snippets(case_facts: str) -> list[str]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", case_facts) if sentence.strip()]
    if not sentences and case_facts.strip():
        sentences = [case_facts.strip()]
    return [sentence[:500] for sentence in sentences[:8]]


def _adverse_material(strategy_response: StrategyDraftResponse | None) -> list[str]:
    if strategy_response is None:
        return []
    adverse: list[str] = []
    adverse.extend(counter.counterargument for counter in strategy_response.counterarguments)
    if strategy_response.reasoning_pack is not None:
        adverse.extend(argument.opposing_argument for argument in strategy_response.reasoning_pack.for_against_brief)
        for issue in strategy_response.reasoning_pack.issue_matrix:
            adverse.extend(issue.facts_against)
    return _dedupe_text(adverse)


def _missing_evidence_tasks(strategy_response: StrategyDraftResponse | None) -> list[str]:
    if strategy_response is None:
        return []
    tasks: list[str] = []
    tasks.extend(strategy_response.missing_authorities)
    tasks.extend(query.purpose for query in strategy_response.next_retrieval_questions)
    if strategy_response.reasoning_pack is not None:
        tasks.extend(strategy_response.reasoning_pack.missing_evidence_checklist)
        tasks.extend(strategy_response.reasoning_pack.lawyer_review_pack.questions_for_client)
        tasks.extend(strategy_response.reasoning_pack.lawyer_review_pack.questions_for_lawyer)
    return _dedupe_text(tasks)


def _reviewer_summary(
    *,
    research_pack: LegalResearchPack,
    strategy_response: StrategyDraftResponse | None,
    clarification_count: int,
    authority_candidate_count: int,
) -> str:
    claim_count = len(strategy_response.claims) if strategy_response else 0
    reasoning_present = bool(strategy_response and strategy_response.reasoning_pack is not None)
    return (
        f"Agentic research plan uses sealed pack {research_pack.pack_id} with {len(research_pack.items)} items, "
        f"{claim_count} cited claims, reasoning_pack_present={reasoning_present}, "
        f"{authority_candidate_count} non-citable authority candidates, and {clarification_count} clarification needs."
    )


def _candidate_title(text: str) -> str:
    return text[:120].rstrip(".:; ") or "Missing authority candidate"


def _candidate_type(text: str) -> str:
    lowered = text.lower()
    if "supreme court" in lowered:
        return "Supreme Court case"
    if "court of appeal" in lowered:
        return "Court of Appeal case"
    if "gazette" in lowered:
        return "Gazette"
    if "act" in lowered or "section" in lowered or "statutory" in lowered:
        return "Act"
    if "nipo" in lowered:
        return "Official registry material"
    return "Missing authority task"


def _authority_expansion_query(candidate: AuthorityExpansionCandidate) -> str:
    query_parts = [
        candidate.title,
        candidate.citation_or_identifier,
        candidate.authority_type,
        candidate.source_hint,
    ]
    query = " ".join(part.strip() for part in query_parts if part and part.strip())
    return query[:500].strip() or candidate.title


def _authority_expansion_query_class(candidate: AuthorityExpansionCandidate) -> QueryClass:
    text = f"{candidate.authority_type} {candidate.title} {candidate.citation_or_identifier}".lower()
    if any(term in text for term in ("act", "section", "gazette", "regulation", "ordinance", "statutory")):
        return QueryClass.STATUTE_LOOKUP
    if any(term in text for term in ("supreme court", "court of appeal", "case", "appeal", "judgment")):
        return QueryClass.CASE_LAW_LOOKUP
    return QueryClass.GENERAL_RESEARCH


def _authority_expansion_filters(candidate: AuthorityExpansionCandidate) -> dict[str, Any]:
    text = f"{candidate.authority_type} {candidate.title} {candidate.citation_or_identifier}".lower()
    authority_levels = [1]
    document_types: list[str] = []
    if any(term in text for term in ("act", "section", "gazette", "regulation", "ordinance", "statutory")):
        authority_levels.append(2)
        document_types.extend(["statute", "gazette", "regulation"])
    if any(term in text for term in ("supreme court", "court of appeal", "case", "appeal", "judgment")):
        authority_levels.append(3)
        document_types.extend(["judgment", "case_law"])
    return {
        "require_official": True,
        "authority_levels": sorted(set(authority_levels)),
        "document_types": _dedupe_text(document_types),
    }


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


_REASONING_OUTPUTS = {"for_against_brief", "preliminary_legal_opinion", "lawyer_review_pack"}
