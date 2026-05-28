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


class CitedClaim(BaseModel):
    claim: str = Field(min_length=1)
    pack_item_ids: list[str] = Field(min_length=1)
    confidence: str = "needs_lawyer_review"


RiskSeverity = Literal["low", "medium", "high", "critical"]


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
    status: str
    reviewStatus: str | None = None
    contentPreview: str
    claimCount: int = Field(ge=0)


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
