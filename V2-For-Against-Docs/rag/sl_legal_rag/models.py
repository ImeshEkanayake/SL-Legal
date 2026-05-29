from __future__ import annotations

from datetime import datetime
try:
    from enum import StrEnum
except ImportError:  # Python < 3.11 compatibility for local tooling.
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class QueryClass(StrEnum):
    STATUTE_LOOKUP = "statute_lookup"
    CASE_LAW_LOOKUP = "case_law_lookup"
    PROCEDURE = "procedure"
    STRATEGY = "strategy"
    FACTUAL_MATCH = "factual_match"
    CITATION_VALIDATION = "citation_validation"
    MISSING_SOURCE_CHECK = "missing_source_check"
    GENERAL_RESEARCH = "general_research"


CertaintyLabel = Literal["explicitly_stated", "inferred", "ambiguous", "missing", "contradictory"]


class RetrievalFilters(BaseModel):
    document_types: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    language: str | None = "English"
    authority_levels: list[int] = Field(default_factory=list)
    require_official: bool = False

    @field_validator("authority_levels", mode="before")
    @classmethod
    def normalize_authority_levels(cls, value: Any) -> list[int]:
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        normalized: list[int] = []
        labels = {
            "primary": 1,
            "official": 1,
            "statute": 2,
            "legislation": 2,
            "case_law": 3,
            "secondary": 6,
        }
        for item in values:
            if isinstance(item, int):
                normalized.append(item)
                continue
            text = str(item).strip().lower()
            if text.isdigit():
                normalized.append(int(text))
            elif text in labels:
                normalized.append(labels[text])
        return normalized


class SourceSpan(BaseModel):
    source_id: str = "user_input"
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    quote: str = ""


class StructuredParty(BaseModel):
    name: str
    role: str = "unknown"
    certainty_label: CertaintyLabel = "explicitly_stated"
    source_spans: list[SourceSpan] = Field(default_factory=list)


class StructuredCaseFact(BaseModel):
    fact_id: str
    fact_text: str
    fact_category: str
    certainty_label: CertaintyLabel
    materiality: str = "unknown"
    disputed_status: str = "unknown"
    source_spans: list[SourceSpan] = Field(default_factory=list)


class StructuredTimelineEvent(BaseModel):
    event_id: str
    event_text: str
    event_date: str | None = None
    date_label: str | None = None
    certainty_label: CertaintyLabel = "explicitly_stated"
    source_spans: list[SourceSpan] = Field(default_factory=list)


class StructuredCaseIssue(BaseModel):
    issue_id: str
    issue_text: str
    issue_type: str
    priority: str = "normal"
    certainty_label: CertaintyLabel = "inferred"
    inferred_reason: str | None = None
    supporting_fact_ids: list[str] = Field(default_factory=list)


class StructuredObservation(BaseModel):
    item: str
    certainty_label: CertaintyLabel = "missing"
    source_spans: list[SourceSpan] = Field(default_factory=list)


class RetrievalQueryVariant(BaseModel):
    query: str
    query_class: QueryClass = QueryClass.GENERAL_RESEARCH
    purpose: str
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class MeceCaseStructure(BaseModel):
    schema_version: str = "mece_case_structure.v1"
    source_id: str = "user_input"
    raw_input_sha256: str
    case_summary: str
    parties: list[StructuredParty] = Field(default_factory=list)
    facts: list[StructuredCaseFact] = Field(default_factory=list)
    timeline: list[StructuredTimelineEvent] = Field(default_factory=list)
    issues: list[StructuredCaseIssue] = Field(default_factory=list)
    missing_information: list[StructuredObservation] = Field(default_factory=list)
    ambiguities: list[StructuredObservation] = Field(default_factory=list)
    contradictions: list[StructuredObservation] = Field(default_factory=list)
    retrieval_queries: list[RetrievalQueryVariant] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("missing_information", "ambiguities", "contradictions", mode="before")
    @classmethod
    def normalize_observations(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, str):
                normalized.append({"item": item})
            elif isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"item": str(item)})
        return normalized


class ResearchQueryRequest(BaseModel):
    query: str = Field(min_length=3)
    query_class: QueryClass = QueryClass.GENERAL_RESEARCH
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    max_pack_items: int = Field(default=24, ge=1, le=100)
    max_pack_tokens: int = Field(default=12000, ge=1000, le=60000)
    case_id: str | None = None
    parent_pack_id: str | None = None
    source_thread_id: str | None = None
    source_agent_run_id: str | None = None
    created_by_user_id: str | None = None
    purpose: str = "legal_research"


class CaseStructureRequest(BaseModel):
    raw_input: str = Field(min_length=10)
    max_completion_tokens: int = Field(default=8192, ge=1000, le=20000)


class PackItem(BaseModel):
    pack_item_id: str
    chunk_id: str
    document_id: str
    title: str
    document_type: str
    source_id: str
    authority_level: int
    year: int | None = None
    citation: str
    page_start: int | None = None
    page_end: int | None = None
    text: str
    fused_score: float
    selection_reason: str
    source_url: str | None = None
    local_path: str | None = None
    token_estimate: int | None = Field(default=None, ge=0)
    scoring_breakdown: dict[str, Any] = Field(default_factory=dict)
    retrieval_trace: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackItemSourcePage(BaseModel):
    page_id: str
    page_number: int
    text: str
    extraction_method: str
    ocr_confidence: float | None = None
    quality_flags: list[str] = Field(default_factory=list)


class PackItemSourceAnchor(BaseModel):
    anchor_id: str
    page_id: str | None = None
    page_number: int | None = None
    anchor_index: int
    char_start: int | None = None
    char_end: int | None = None
    quote: str
    match_method: str
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackItemSourceResponse(BaseModel):
    pack_id: str
    pack_item_id: str
    chunk_id: str
    document_id: str
    title: str
    document_type: str
    source_id: str
    authority_level: int
    year: int | None = None
    citation: str
    page_start: int | None = None
    page_end: int | None = None
    selected_text: str
    context_text: str
    context_source: Literal["page_text", "research_pack_item", "retrieval_chunk"]
    source_url: str | None = None
    local_path: str | None = None
    absolute_local_path: str | None = None
    local_file_exists: bool = False
    page_text_available: bool = False
    pages: list[PackItemSourcePage] = Field(default_factory=list)
    anchors: list[PackItemSourceAnchor] = Field(default_factory=list)
    anchor_status: Literal["anchored", "not_anchored"] = "not_anchored"
    source_quality_flags: list[str] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class LegalResearchPack(BaseModel):
    schema_version: str = "legal_research_pack.v1"
    pack_id: str
    pack_version: int = Field(default=1, ge=1)
    parent_pack_id: str | None = None
    query: str
    query_class: QueryClass
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    retrieval_config: dict[str, Any]
    items: list[PackItem]
    missing_source_summary: str | None = None
    token_count: int | None = Field(default=None, ge=0)
    source_warnings: list[str] = Field(default_factory=list)
    retrieval_trace: list[dict[str, Any]] = Field(default_factory=list)
    pack_hash: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def allowed_pack_item_ids(self) -> set[str]:
        return {item.pack_item_id for item in self.items}


VerificationStatus = Literal[
    "verified",
    "partially_verified",
    "assumed",
    "missing_evidence",
    "requires_case_law",
    "requires_lawyer_review",
]
ReasoningOutputType = Literal["for_against_brief", "preliminary_legal_opinion", "lawyer_review_pack"]
ArgumentStrength = Literal["high", "medium", "low", "unknown"]

AgentResearchToolName = Literal[
    "case_intake_structurer",
    "search_database",
    "expand_authorities",
    "official_source_check",
    "ask_clarification",
    "answer_from_pack",
    "lawyer_review_pack",
]
AgentToolStatus = Literal["planned", "completed", "empty", "failed", "requires_clarification", "blocked"]
AgentSourceBoundary = Literal[
    "user_input",
    "database",
    "sealed_pack",
    "candidate_authorities",
    "official_source",
    "generated_draft",
]
AuthorityCandidateStatus = Literal[
    "candidate_unverified",
    "candidate_metadata_verified",
    "promoted_to_sealed_pack",
    "rejected",
    "requires_lawyer_verification",
]
ClarificationCategory = Literal[
    "client_position",
    "parties",
    "jurisdiction",
    "dates",
    "relief_sought",
    "registration_number",
    "case_number",
    "procedural_posture",
    "material_fact",
]

TOOL_ALLOWED_SOURCE_BOUNDARIES: dict[str, set[str]] = {
    "case_intake_structurer": {"user_input"},
    "search_database": {"database"},
    "expand_authorities": {"candidate_authorities", "database"},
    "official_source_check": {"official_source"},
    "ask_clarification": {"user_input"},
    "answer_from_pack": {"sealed_pack"},
    "lawyer_review_pack": {"sealed_pack", "generated_draft"},
}


class AgentToolTrace(BaseModel):
    schema_version: str = "agent_tool_trace.v1"
    trace_id: str = Field(min_length=1)
    tool_name: AgentResearchToolName
    purpose: str = Field(min_length=1)
    source_boundary: AgentSourceBoundary
    input_summary: dict[str, Any] = Field(default_factory=dict)
    result_count: int | None = Field(default=None, ge=0)
    status: AgentToolStatus = "planned"
    selected_outputs: list[dict[str, Any]] = Field(default_factory=list)
    reviewer_note: str = Field(min_length=1)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_trace_contract(self) -> "AgentToolTrace":
        allowed = TOOL_ALLOWED_SOURCE_BOUNDARIES[self.tool_name]
        if self.source_boundary not in allowed:
            raise ValueError(f"{self.tool_name} cannot use source boundary {self.source_boundary}")
        if self.status in {"completed", "empty"} and self.result_count is None:
            raise ValueError("completed or empty tool traces require result_count")
        if self.status == "completed" and self.result_count == 0:
            raise ValueError("completed tool traces require a positive result_count; use empty for zero results")
        if self.status == "failed" and "error" not in self.metadata:
            raise ValueError("failed tool traces require metadata.error")
        return self


class AuthorityExpansionCandidate(BaseModel):
    schema_version: str = "authority_expansion_candidate.v1"
    candidate_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authority_type: str = Field(min_length=1)
    citation_or_identifier: str = Field(min_length=1)
    source_boundary: Literal["candidate_authorities", "official_source"] = "candidate_authorities"
    originating_tool_trace_id: str = Field(min_length=1)
    source_hint: str = Field(min_length=1)
    status: AuthorityCandidateStatus = "candidate_unverified"
    verification_status: VerificationStatus = "requires_lawyer_review"
    promoted_pack_item_ids: list[str] = Field(default_factory=list)
    reviewer_note: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def citable(self) -> bool:
        return self.status == "promoted_to_sealed_pack" and bool(self.promoted_pack_item_ids)

    @model_validator(mode="after")
    def validate_candidate_promotion_boundary(self) -> "AuthorityExpansionCandidate":
        if self.status == "promoted_to_sealed_pack" and not self.promoted_pack_item_ids:
            raise ValueError("promoted authority candidates require promoted_pack_item_ids")
        if self.status != "promoted_to_sealed_pack" and self.promoted_pack_item_ids:
            raise ValueError("unpromoted authority candidates must not carry promoted pack item ids")
        if self.status == "candidate_metadata_verified" and self.verification_status == "verified":
            raise ValueError("candidate metadata verification is not enough for citable verified legal authority")
        return self


class ClarificationNeed(BaseModel):
    clarification_id: str = Field(min_length=1)
    category: ClarificationCategory
    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    blocks_preliminary_opinion: bool = True
    suggested_retrieval_after_answer: list[RetrievalQueryVariant] = Field(default_factory=list)


class MatterMemory(BaseModel):
    schema_version: str = "matter_memory.v1"
    matter_id: str = Field(min_length=1)
    case_id: str | None = None
    client_position: str | None = None
    selected_authority_ids: list[str] = Field(default_factory=list)
    sealed_pack_ids: list[str] = Field(default_factory=list)
    candidate_authorities: list[AuthorityExpansionCandidate] = Field(default_factory=list)
    client_facts: list[str] = Field(default_factory=list)
    adverse_material: list[str] = Field(default_factory=list)
    missing_evidence_tasks: list[str] = Field(default_factory=list)
    clarification_needs: list[ClarificationNeed] = Field(default_factory=list)
    tool_traces: list[AgentToolTrace] = Field(default_factory=list)
    review_state: dict[str, Any] = Field(default_factory=dict)

    @property
    def promoted_pack_item_ids(self) -> set[str]:
        return {
            pack_item_id
            for candidate in self.candidate_authorities
            if candidate.citable
            for pack_item_id in candidate.promoted_pack_item_ids
        }

    @property
    def unresolved_blocking_clarifications(self) -> list[ClarificationNeed]:
        return [need for need in self.clarification_needs if need.blocks_preliminary_opinion]

    @model_validator(mode="after")
    def validate_memory_trace_references(self) -> "MatterMemory":
        trace_ids = {trace.trace_id for trace in self.tool_traces}
        missing_trace_ids = sorted(
            {
                candidate.originating_tool_trace_id
                for candidate in self.candidate_authorities
                if candidate.originating_tool_trace_id not in trace_ids
            }
        )
        if missing_trace_ids:
            raise ValueError(f"authority candidates reference unknown tool traces: {', '.join(missing_trace_ids)}")
        if any(candidate.citable for candidate in self.candidate_authorities) and not self.sealed_pack_ids:
            raise ValueError("promoted authority candidates require at least one sealed_pack_id in matter memory")
        return self


class AgentResearchPlan(BaseModel):
    schema_version: str = "agent_research_plan.v1"
    plan_id: str = Field(min_length=1)
    matter_id: str = Field(min_length=1)
    requested_output: ReasoningOutputType | Literal["strategy_report"] = "lawyer_review_pack"
    tool_traces: list[AgentToolTrace] = Field(min_length=1)
    clarification_needs: list[ClarificationNeed] = Field(default_factory=list)
    authority_candidates: list[AuthorityExpansionCandidate] = Field(default_factory=list)
    reviewer_summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_plan_sequence(self) -> "AgentResearchPlan":
        trace_names = [trace.tool_name for trace in self.tool_traces]
        if "answer_from_pack" in trace_names and "search_database" not in trace_names:
            raise ValueError("answer_from_pack requires a prior search_database trace")
        if "official_source_check" in trace_names and "expand_authorities" not in trace_names:
            raise ValueError("official_source_check requires a prior expand_authorities trace")
        if self.clarification_needs and "ask_clarification" not in trace_names:
            raise ValueError("clarification needs require an ask_clarification trace")
        trace_ids = {trace.trace_id for trace in self.tool_traces}
        missing_trace_ids = sorted(
            {
                candidate.originating_tool_trace_id
                for candidate in self.authority_candidates
                if candidate.originating_tool_trace_id not in trace_ids
            }
        )
        if missing_trace_ids:
            raise ValueError(f"authority candidates reference unknown tool traces: {', '.join(missing_trace_ids)}")
        return self


class ResearchPackExpansionRequest(BaseModel):
    query: str = Field(min_length=3)
    query_class: QueryClass = QueryClass.GENERAL_RESEARCH
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    max_pack_items: int = Field(default=24, ge=1, le=100)
    max_pack_tokens: int = Field(default=12000, ge=1000, le=60000)
    case_id: str | None = None
    source_thread_id: str | None = None
    source_agent_run_id: str | None = None
    purpose: str = "pack_expansion"

    def to_research_query_request(self, *, parent_pack_id: str, case_id: str | None) -> ResearchQueryRequest:
        return ResearchQueryRequest(
            query=self.query,
            query_class=self.query_class,
            filters=self.filters,
            max_pack_items=self.max_pack_items,
            max_pack_tokens=self.max_pack_tokens,
            case_id=self.case_id or case_id,
            parent_pack_id=parent_pack_id,
            source_thread_id=self.source_thread_id,
            source_agent_run_id=self.source_agent_run_id,
            purpose=self.purpose,
        )


AuthorityPackExpansionStatus = Literal["planned", "partially_executed", "executed", "cancelled"]


class AuthorityPackExpansionExecutionRecord(BaseModel):
    schema_version: str = "authority_pack_expansion_execution.v1"
    request_index: int = Field(ge=0)
    child_pack_id: str = Field(min_length=1)
    child_pack_hash: str = Field(min_length=1)
    item_count: int = Field(ge=0)
    executed_by_user_id: str | None = None
    executed_at: datetime
    request_query_sha256: str = Field(min_length=64, max_length=64)


class AuthorityPackExpansionPlan(BaseModel):
    schema_version: str = "authority_pack_expansion_plan.v1"
    plan_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    draft_id: str = Field(min_length=1)
    review_item_id: str = Field(min_length=1)
    parent_pack_id: str = Field(min_length=1)
    source: Literal["approved_authority_candidate_review"] = "approved_authority_candidate_review"
    status: AuthorityPackExpansionStatus = "planned"
    candidate_ids: list[str] = Field(min_length=1)
    expansion_requests: list[ResearchPackExpansionRequest] = Field(min_length=1)
    executed_pack_ids: list[str] = Field(default_factory=list)
    execution_records: list[AuthorityPackExpansionExecutionRecord] = Field(default_factory=list)
    citable: bool = False
    reviewer_note: str = Field(
        default=(
            "Planned expansion only; candidate authorities remain non-citable until retrieved, "
            "anchored, verified, and sealed into a research pack."
        ),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_expansion_boundary(self) -> "AuthorityPackExpansionPlan":
        if self.citable:
            raise ValueError("authority expansion plans must not be citable")
        if not self.candidate_ids:
            raise ValueError("authority expansion plans require candidate_ids")
        if self.status == "executed" and not self.executed_pack_ids:
            raise ValueError("executed authority expansion plans require executed_pack_ids")
        executed_pack_ids = [record.child_pack_id for record in self.execution_records]
        if self.executed_pack_ids != executed_pack_ids:
            raise ValueError("executed_pack_ids must match execution record child pack ids")
        request_indexes = [record.request_index for record in self.execution_records]
        if len(request_indexes) != len(set(request_indexes)):
            raise ValueError("authority expansion execution records require unique request indexes")
        if any(index >= len(self.expansion_requests) for index in request_indexes):
            raise ValueError("authority expansion execution record references unknown request index")
        for request in self.expansion_requests:
            if not request.filters.require_official:
                raise ValueError("authority expansion requests must require official-source retrieval")
            if request.purpose != "authority_candidate_pack_expansion":
                raise ValueError("authority expansion requests must use authority_candidate_pack_expansion purpose")
        return self


class CitedClaim(BaseModel):
    claim: str = Field(min_length=1)
    pack_item_ids: list[str] = Field(min_length=1)
    confidence: str = "needs_lawyer_review"


RiskSeverity = Literal["low", "medium", "high", "critical"]
EvidenceReviewStatus = Literal["pending", "approved", "changes_requested", "rejected"]


class EvidenceStance(StrEnum):
    SUPPORTS_CLAIM = "supports_claim"
    CONTRADICTS_CLAIM = "contradicts_claim"
    MIXED = "mixed"
    CONTEXT = "context"


EVIDENCE_STANCE_TO_CITATION_ROLE: dict[str, str] = {
    EvidenceStance.SUPPORTS_CLAIM: "support",
    EvidenceStance.CONTRADICTS_CLAIM: "adverse",
    EvidenceStance.MIXED: "mixed",
    EvidenceStance.CONTEXT: "context",
}
EVIDENCE_CITATION_ROLE_TO_STANCE: dict[str, EvidenceStance] = {
    role: stance for stance, role in EVIDENCE_STANCE_TO_CITATION_ROLE.items()
}


def citation_role_for_evidence_stance(stance: EvidenceStance | str) -> str:
    return EVIDENCE_STANCE_TO_CITATION_ROLE[_normalize_evidence_stance(stance)]


def evidence_stance_for_citation_role(citation_role: str) -> EvidenceStance:
    normalized = citation_role.strip().lower()
    if normalized not in EVIDENCE_CITATION_ROLE_TO_STANCE:
        raise ValueError(f"Unsupported evidence citation role: {citation_role}")
    return EVIDENCE_CITATION_ROLE_TO_STANCE[normalized]


def _normalize_evidence_stance(stance: EvidenceStance | str) -> EvidenceStance:
    if isinstance(stance, EvidenceStance):
        return stance
    return EvidenceStance(str(stance))


class ClaimEvidenceAssessmentRequest(BaseModel):
    schema_version: str = "claim_evidence_assessment.v1"
    claim_id: str | None = None
    claim_text: str | None = Field(default=None, min_length=1)
    pack_id: str = Field(min_length=1)
    pack_item_id: str = Field(min_length=1)
    stance: EvidenceStance
    rationale: str = Field(min_length=1)
    confidence_score: float = Field(ge=0, le=1)
    risk_level: RiskSeverity = "medium"
    source_quote: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    review_status: EvidenceReviewStatus = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("claim_id", "claim_text", "rationale", "source_quote", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_assessment_contract(self) -> "ClaimEvidenceAssessmentRequest":
        if not self.claim_id and not self.claim_text:
            raise ValueError("claim_text is required when claim_id is not supplied")
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        if self.stance == EvidenceStance.MIXED and not self.rationale.strip():
            raise ValueError("mixed evidence requires an assessment rationale")
        return self

    @property
    def citation_role(self) -> str:
        return citation_role_for_evidence_stance(self.stance)


class ClaimEvidenceAssessment(BaseModel):
    schema_version: str = "claim_evidence_assessment.v1"
    assessment_id: str
    case_id: str
    claim_id: str
    claim_text: str
    pack_id: str
    pack_item_id: str
    stance: EvidenceStance
    citation_role: str
    rationale: str
    confidence_score: float = Field(ge=0, le=1)
    risk_level: RiskSeverity = "medium"
    source_quote: str
    page_start: int | None = None
    page_end: int | None = None
    review_status: EvidenceReviewStatus | str = "pending"
    document_id: str
    title: str
    document_type: str
    source_id: str
    authority_level: int
    year: int | None = None
    citation: str
    source_url: str | None = None
    local_path: str | None = None
    anchor_count: int = 0
    source_endpoint: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceAssessmentStanceGroup(BaseModel):
    stance: EvidenceStance
    count: int = Field(ge=0)
    items: list[ClaimEvidenceAssessment] = Field(default_factory=list)


class EvidenceAssessmentGroupedResponse(BaseModel):
    case_id: str
    claim_id: str | None = None
    pack_id: str | None = None
    stance: EvidenceStance | None = None
    total_count: int = Field(ge=0)
    groups: list[EvidenceAssessmentStanceGroup] = Field(default_factory=list)


class EvidenceAssessmentCreateResponse(BaseModel):
    case_id: str
    assessment: ClaimEvidenceAssessment


class CounterargumentSimulation(BaseModel):
    counterargument: str = Field(min_length=1)
    supporting_pack_item_ids: list[str] = Field(default_factory=list)
    response: str = Field(min_length=1)
    response_pack_item_ids: list[str] = Field(default_factory=list)
    risk_level: RiskSeverity = "medium"


class StrategyRiskRanking(BaseModel):
    risk: str = Field(min_length=1)
    severity: RiskSeverity = "medium"
    rationale: str = Field(min_length=1)
    pack_item_ids: list[str] = Field(default_factory=list)
    mitigation: str | None = None


class AuthorityVerification(BaseModel):
    authority_id: str
    title: str = Field(min_length=1)
    authority_type: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    pack_item_ids: list[str] = Field(default_factory=list)
    section: str = "to_be_verified"
    official_source_checked: bool = False
    amendment_checked: bool = False
    case_law_checked: bool = False
    procedural_rule_checked: bool = False
    verification_status: VerificationStatus = "requires_lawyer_review"
    notes: str = ""

    @model_validator(mode="after")
    def require_verification_status_for_unchecked_authorities(self) -> "AuthorityVerification":
        if self.verification_status == "verified" and not (
            self.official_source_checked and self.amendment_checked
        ):
            raise ValueError("verified authorities require official source and amendment checks")
        return self


class LegalElement(BaseModel):
    element_id: str
    element: str = Field(min_length=1)
    supporting_facts: list[str] = Field(default_factory=list)
    opposing_facts: list[str] = Field(default_factory=list)
    authority_ids: list[str] = Field(default_factory=list)
    pack_item_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = "requires_lawyer_review"


class IssueMatrixItem(BaseModel):
    issue_id: str
    issue: str = Field(min_length=1)
    legal_area: str = Field(min_length=1)
    elements: list[LegalElement] = Field(min_length=1)
    authority_ids: list[str] = Field(default_factory=list)
    facts_supporting: list[str] = Field(default_factory=list)
    facts_against: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    verification_status: VerificationStatus = "requires_lawyer_review"


class FactLawMapping(BaseModel):
    issue_id: str
    fact: str = Field(min_length=1)
    legal_question: str = Field(min_length=1)
    authority_id: str | None = None
    specific_section: str = "to_be_verified"
    supporting_reasoning: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    missing_documents: list[str] = Field(default_factory=list)
    pack_item_ids: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = "requires_lawyer_review"
    lawyer_verification_required: bool = True

    @model_validator(mode="after")
    def require_grounding_or_verification(self) -> "FactLawMapping":
        if not self.pack_item_ids and self.verification_status == "verified":
            raise ValueError("verified fact-to-law mappings require at least one pack_item_id")
        if not self.pack_item_ids and not self.lawyer_verification_required:
            raise ValueError("ungrounded fact-to-law mappings require lawyer verification")
        return self


class ForAgainstLegalBasis(BaseModel):
    authority_id: str | None = None
    authority: str = Field(min_length=1)
    section: str = "to_be_verified"
    proposition: str = Field(min_length=1)
    pack_item_ids: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = "requires_lawyer_review"

    @model_validator(mode="after")
    def require_pack_citation_or_verification(self) -> "ForAgainstLegalBasis":
        if not self.pack_item_ids and self.verification_status == "verified":
            raise ValueError("verified legal basis entries require at least one pack_item_id")
        return self


class ForAgainstArgument(BaseModel):
    issue_id: str
    issue: str = Field(min_length=1)
    legal_basis: list[ForAgainstLegalBasis] = Field(default_factory=list)
    facts_relied_on: list[str] = Field(default_factory=list)
    client_argument: str = Field(min_length=1)
    opposing_argument: str = Field(min_length=1)
    rebuttal: str = Field(min_length=1)
    weaknesses: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    strength: ArgumentStrength = "unknown"
    confidence: float = Field(ge=0, le=1)
    requires_lawyer_verification: bool = True
    pack_item_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_balanced_argument(self) -> "ForAgainstArgument":
        basis_pack_ids = {item_id for basis in self.legal_basis for item_id in basis.pack_item_ids}
        if not self.pack_item_ids and basis_pack_ids:
            self.pack_item_ids = sorted(basis_pack_ids)
        if not self.requires_lawyer_verification:
            raise ValueError("for/against arguments must require lawyer verification")
        return self


class PreliminaryLegalOpinion(BaseModel):
    matter: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    important_qualification: str = Field(min_length=1)
    assumed_facts: list[str] = Field(min_length=1)
    documents_reviewed: list[str] = Field(min_length=1)
    issues: list[str] = Field(min_length=1)
    applicable_law: list[str] = Field(min_length=1)
    analysis: str = Field(min_length=1)
    preliminary_opinion: str = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    recommended_next_steps: list[str] = Field(min_length=1)
    conclusion: str = Field(min_length=1)
    lawyer_verification_required: bool = True

    @model_validator(mode="after")
    def enforce_preliminary_cautious_language(self) -> "PreliminaryLegalOpinion":
        combined = " ".join(
            [
                self.important_qualification,
                self.analysis,
                self.preliminary_opinion,
                self.conclusion,
            ]
        ).lower()
        banned = ["final legal advice", "will win", "guaranteed", "strong case"]
        if any(term in combined for term in banned):
            raise ValueError("preliminary legal opinion contains unsafe final-advice wording")
        required = ["preliminary", "lawyer", "verification"]
        if not all(term in combined for term in required):
            raise ValueError("preliminary legal opinion must use cautious lawyer-verification language")
        if not self.lawyer_verification_required:
            raise ValueError("preliminary legal opinion must require lawyer verification")
        return self


class LawyerReviewPack(BaseModel):
    one_page_case_summary: str = Field(min_length=1)
    issue_matrix_ids: list[str] = Field(min_length=1)
    authority_ids: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(min_length=1)
    questions_for_client: list[str] = Field(min_length=1)
    questions_for_lawyer: list[str] = Field(min_length=1)
    review_notes: list[str] = Field(default_factory=list)


class ReasoningPackOutput(BaseModel):
    schema_version: str = "reasoning_pack.v1"
    output_type: ReasoningOutputType = "lawyer_review_pack"
    authority_verifications: list[AuthorityVerification] = Field(min_length=1)
    issue_matrix: list[IssueMatrixItem] = Field(min_length=1)
    fact_to_law_mappings: list[FactLawMapping] = Field(min_length=1)
    for_against_brief: list[ForAgainstArgument] = Field(min_length=1)
    missing_evidence_checklist: list[str] = Field(min_length=1)
    preliminary_legal_opinion: PreliminaryLegalOpinion
    lawyer_review_pack: LawyerReviewPack
    lawyer_verification_required: bool = True
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reasoning_pack_contract(self) -> "ReasoningPackOutput":
        issue_ids = {item.issue_id for item in self.issue_matrix}
        mapped_issue_ids = {item.issue_id for item in self.fact_to_law_mappings}
        argument_issue_ids = {item.issue_id for item in self.for_against_brief}
        unknown_mappings = sorted(mapped_issue_ids.difference(issue_ids))
        unknown_arguments = sorted(argument_issue_ids.difference(issue_ids))
        if unknown_mappings:
            raise ValueError(f"fact-to-law mappings reference unknown issues: {', '.join(unknown_mappings)}")
        if unknown_arguments:
            raise ValueError(f"for/against arguments reference unknown issues: {', '.join(unknown_arguments)}")
        if not self.lawyer_verification_required:
            raise ValueError("reasoning packs must require lawyer verification")
        if not any(item.opposing_argument.strip() for item in self.for_against_brief):
            raise ValueError("reasoning packs require adverse or opposing analysis")
        return self

    def all_pack_item_ids(self) -> set[str]:
        item_ids = {item_id for authority in self.authority_verifications for item_id in authority.pack_item_ids}
        for issue in self.issue_matrix:
            for element in issue.elements:
                item_ids.update(element.pack_item_ids)
        for mapping in self.fact_to_law_mappings:
            item_ids.update(mapping.pack_item_ids)
        for argument in self.for_against_brief:
            item_ids.update(argument.pack_item_ids)
            for basis in argument.legal_basis:
                item_ids.update(basis.pack_item_ids)
        return item_ids


class StrategyDraftRequest(BaseModel):
    case_facts: str = Field(min_length=10)
    pack_id: str = Field(min_length=1)
    requested_output: str = "strategy_report"
    case_id: str | None = None
    thread_id: str | None = None
    message_id: str | None = None
    agent_run_id: str | None = None
    created_by_user_id: str | None = None
    assigned_review_user_id: str | None = None


class StrategyDraftResponse(BaseModel):
    pack_id: str
    answer: str
    claims: list[CitedClaim]
    reasoning_pack: ReasoningPackOutput | None = None
    counterarguments: list[CounterargumentSimulation] = Field(default_factory=list)
    risk_rankings: list[StrategyRiskRanking] = Field(default_factory=list)
    next_retrieval_questions: list[RetrievalQueryVariant] = Field(default_factory=list)
    missing_authorities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citation_validation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_citations_for_legal_claims(self) -> "StrategyDraftResponse":
        if not self.claims:
            raise ValueError("strategy output must contain cited claims")
        return self

    def all_pack_item_ids(self) -> set[str]:
        item_ids = {item_id for claim in self.claims for item_id in claim.pack_item_ids}
        for counterargument in self.counterarguments:
            item_ids.update(counterargument.supporting_pack_item_ids)
            item_ids.update(counterargument.response_pack_item_ids)
        for risk in self.risk_rankings:
            item_ids.update(risk.pack_item_ids)
        if self.reasoning_pack is not None:
            item_ids.update(self.reasoning_pack.all_pack_item_ids())
        return item_ids


class PersistedStrategyDraftResponse(StrategyDraftResponse):
    case_id: str
    thread_id: str | None = None
    draft_id: str
    message_id: str | None = None
    agent_run_id: str
    claim_ids: list[str]
    draft_review_item_id: str
    claim_review_item_ids: list[str]
    reasoning_review_item_ids: list[str] = Field(default_factory=list)


class ReviewQueueItem(BaseModel):
    review_item_id: str
    case_id: str
    item_type: str
    item_id: str
    status: str
    priority: str
    assigned_to_user_id: str | None = None
    reviewed_by_user_id: str | None = None
    decision: str | None = None
    comment: str | None = None
    due_at: datetime | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    item_title: str
    item_excerpt: str
    pack_id: str | None = None
    thread_id: str | None = None


class ReviewQueueResponse(BaseModel):
    case_id: str
    status: str | None = None
    item_type: str | None = None
    items: list[ReviewQueueItem]


ReviewDecision = Literal["approved", "rejected", "changes_requested"]


class ReviewDecisionRequest(BaseModel):
    decision: ReviewDecision
    comment: str | None = None

    @model_validator(mode="after")
    def require_comment_for_negative_decisions(self) -> "ReviewDecisionRequest":
        if self.decision in {"rejected", "changes_requested"} and not (self.comment or "").strip():
            raise ValueError("comment is required when rejecting or requesting changes")
        return self


class ReviewDecisionResponse(BaseModel):
    case_id: str
    review_item: ReviewQueueItem
    target_item_type: str
    target_item_id: str
    target_status: str
    audit_event_id: int


class AuthorityPackExpansionExecutionResponse(BaseModel):
    case_id: str
    draft_id: str
    plan_id: str
    request_index: int
    status: AuthorityPackExpansionStatus
    parent_pack_id: str
    child_pack_id: str
    item_count: int
    pack_hash: str
    authority_pack_expansion_plan: AuthorityPackExpansionPlan


class DraftSummary(BaseModel):
    draft_id: str
    case_id: str
    thread_id: str | None = None
    pack_id: str | None = None
    draft_type: str
    title: str
    status: str
    version: int
    content_preview: str
    claim_count: int = 0
    review_status: str | None = None
    created_by_agent_run_id: str | None = None
    created_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DraftListResponse(BaseModel):
    case_id: str
    status: str | None = None
    drafts: list[DraftSummary]


class ClaimCitationSummary(BaseModel):
    pack_item_id: str
    citation_role: str
    pack_id: str
    chunk_id: str
    document_id: str
    title: str
    document_type: str
    source_id: str
    authority_level: int
    year: int | None = None
    citation: str
    page_start: int | None = None
    page_end: int | None = None
    source_url: str | None = None
    local_path: str | None = None
    anchor_count: int = 0
    source_endpoint: str


class ClaimSummary(BaseModel):
    claim_id: str
    case_id: str
    thread_id: str | None = None
    message_id: str | None = None
    pack_id: str | None = None
    claim_text: str
    claim_type: str
    support_status: str
    risk_level: str
    citation_count: int = 0
    review_status: str | None = None
    created_by_agent_run_id: str | None = None
    reviewed_by_user_id: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimListResponse(BaseModel):
    case_id: str
    pack_id: str | None = None
    support_status: str | None = None
    draft_id: str | None = None
    claims: list[ClaimSummary]


class ClaimDetail(ClaimSummary):
    citations: list[ClaimCitationSummary] = Field(default_factory=list)
    review_items: list[ReviewQueueItem] = Field(default_factory=list)


class DraftDetail(DraftSummary):
    content_markdown: str
    claims: list[ClaimSummary] = Field(default_factory=list)
    review_items: list[ReviewQueueItem] = Field(default_factory=list)


class AuditEventRecord(BaseModel):
    audit_event_id: int
    organization_id: str | None = None
    case_id: str | None = None
    user_id: str | None = None
    event_type: str
    entity_type: str
    entity_id: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditEventListResponse(BaseModel):
    case_id: str
    event_type: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    next_cursor: str | None = None
    events: list[AuditEventRecord]


AuditEventScope = Literal["user", "organization"]


class AuditEventStreamResponse(BaseModel):
    scope: AuditEventScope
    organization_id: str | None = None
    user_id: str | None = None
    case_id: str | None = None
    event_type: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    next_cursor: str | None = None
    events: list[AuditEventRecord]


class WorkspaceProject(BaseModel):
    projectId: str
    name: str
    activeCaseCount: int = Field(ge=0)


class WorkspaceCase(BaseModel):
    caseId: str
    projectId: str
    title: str
    court: str | None = None
    matterType: str | None = None
    updatedAt: datetime


class WorkspaceChatMessage(BaseModel):
    messageId: str
    threadId: str | None = None
    role: Literal["system", "user", "assistant", "tool", "reviewer"]
    content: str
    createdAt: datetime
    packId: str | None = None


class WorkspaceSourceAnchor(BaseModel):
    anchorId: str
    pageNumber: int | None = None
    quote: str
    confidence: float = Field(ge=0, le=1)


class WorkspaceDocument(BaseModel):
    documentId: str
    title: str
    documentType: str
    citation: str
    sourceId: str
    authorityLevel: int
    pageCount: int = Field(ge=0)
    qualityFlags: list[str] = Field(default_factory=list)
    textPreview: str
    localPath: str | None = None
    sourceUrl: str | None = None
    downloadUrl: str | None = None
    caseFileAvailable: bool = False
    caseFileName: str | None = None
    viewerMimeType: str | None = None
    relevanceScore: float | None = Field(default=None, ge=0, le=1)
    confidenceScore: float | None = Field(default=None, ge=0, le=1)
    relevanceBand: str | None = None
    relevanceRationale: str | None = None


class WorkspaceDocumentFileResponse(BaseModel):
    documentId: str
    title: str
    caseFileAvailable: bool
    caseFileName: str | None = None
    fileUrl: str | None = None
    sourceUrl: str | None = None
    downloadUrl: str | None = None
    viewerMimeType: str | None = None


class WorkspaceResearchPackItem(BaseModel):
    packItemId: str
    packId: str
    documentId: str
    citation: str
    title: str
    authorityLevel: int
    fusedScore: float
    selectionReason: str
    sourceWarnings: list[str] = Field(default_factory=list)
    anchors: list[WorkspaceSourceAnchor] = Field(default_factory=list)


class WorkspaceDraftSummary(BaseModel):
    draftId: str
    title: str
    draftType: str
    requestedOutput: str | None = None
    status: str
    reviewStatus: str | None = None
    contentPreview: str
    claimCount: int = Field(ge=0)
    reasoningPack: ReasoningPackOutput | None = None
    agenticResearchPlan: AgentResearchPlan | None = None
    matterMemory: MatterMemory | None = None
    authorityPackExpansionPlans: list[AuthorityPackExpansionPlan] = Field(default_factory=list)


class WorkspaceReviewItem(BaseModel):
    reviewItemId: str
    itemType: str
    itemTitle: str
    status: str
    priority: str


class CaseWorkspaceSnapshot(BaseModel):
    activeCaseId: str | None = None
    projects: list[WorkspaceProject] = Field(default_factory=list)
    cases: list[WorkspaceCase] = Field(default_factory=list)
    messages: list[WorkspaceChatMessage] = Field(default_factory=list)
    documents: list[WorkspaceDocument] = Field(default_factory=list)
    researchPackItems: list[WorkspaceResearchPackItem] = Field(default_factory=list)
    drafts: list[WorkspaceDraftSummary] = Field(default_factory=list)
    reviewItems: list[WorkspaceReviewItem] = Field(default_factory=list)


class WorkspaceDocumentPageResponse(BaseModel):
    caseId: str
    documents: list[WorkspaceDocument]
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
    hasMore: bool


class WorkspaceChatMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    threadId: str | None = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content is required")
        return normalized


class WorkspaceChatMessageCreateResponse(BaseModel):
    messages: list[WorkspaceChatMessage] = Field(min_length=1)
    packId: str | None = None
    retrievalStatus: Literal["complete", "empty", "failed"] = "complete"


class WorkspaceCaseCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    projectId: str | None = None
    projectName: str | None = Field(default=None, max_length=200)
    caseNumber: str | None = Field(default=None, max_length=120)
    court: str | None = Field(default=None, max_length=200)
    matterType: str | None = Field(default=None, max_length=200)

    @field_validator("title", "projectId", "projectName", "caseNumber", "court", "matterType", mode="before")
    @classmethod
    def strip_optional_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def require_project_reference(self) -> "WorkspaceCaseCreateRequest":
        if not self.projectId and not self.projectName:
            raise ValueError("projectId or projectName is required")
        return self


class WorkspaceCaseCreateResponse(BaseModel):
    caseId: str
    projectId: str


def validate_claims_against_pack(claims: list[CitedClaim], pack: LegalResearchPack) -> list[str]:
    """Return validation errors for citations outside the pack boundary."""

    allowed = pack.allowed_pack_item_ids
    errors: list[str] = []
    for index, claim in enumerate(claims, start=1):
        missing = [item_id for item_id in claim.pack_item_ids if item_id not in allowed]
        if missing:
            errors.append(f"claim {index} cites pack items not present in pack: {', '.join(missing)}")
    return errors
