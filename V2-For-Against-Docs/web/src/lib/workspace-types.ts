export type ReviewStatus = "pending" | "approved" | "changes_requested" | "rejected";

export type WorkspaceProject = {
  projectId: string;
  name: string;
  activeCaseCount: number;
};

export type WorkspaceCase = {
  caseId: string;
  projectId: string;
  title: string;
  court: string | null;
  matterType: string | null;
  updatedAt: string;
};

export type ChatMessage = {
  messageId: string;
  threadId?: string | null;
  role: "system" | "user" | "assistant" | "tool" | "reviewer";
  content: string;
  createdAt: string;
  packId?: string;
};

export type ChatMessageCreateResult = {
  messages: ChatMessage[];
  packId?: string | null;
  retrievalStatus: "complete" | "empty" | "failed";
};

export type SourceAnchor = {
  anchorId: string;
  pageNumber: number | null;
  quote: string;
  confidence: number;
};

export type CaseDocument = {
  documentId: string;
  title: string;
  documentType: string;
  citation: string;
  sourceId: string;
  authorityLevel: number;
  pageCount: number;
  qualityFlags: string[];
  textPreview: string;
  localPath?: string | null;
  sourceUrl?: string | null;
  downloadUrl?: string | null;
  caseFileAvailable: boolean;
  caseFileName?: string | null;
  viewerMimeType?: string | null;
  relevanceScore?: number | null;
  confidenceScore?: number | null;
  relevanceBand?: string | null;
  relevanceRationale?: string | null;
};

export type DocumentFileResult = {
  documentId: string;
  title: string;
  caseFileAvailable: boolean;
  caseFileName?: string | null;
  fileUrl?: string | null;
  sourceUrl?: string | null;
  downloadUrl?: string | null;
  viewerMimeType?: string | null;
};

export type ResearchPackItem = {
  packItemId: string;
  packId: string;
  documentId: string;
  citation: string;
  title: string;
  authorityLevel: number;
  fusedScore: number;
  selectionReason: string;
  sourceWarnings: string[];
  anchors: SourceAnchor[];
};

export type ReasoningPackAuthority = {
  authority_id: string;
  title: string;
  authority_type: string;
  citation: string;
  pack_item_ids: string[];
  section: string;
  official_source_checked: boolean;
  amendment_checked: boolean;
  case_law_checked: boolean;
  procedural_rule_checked: boolean;
  verification_status: string;
  notes: string;
};

export type ReasoningPackElement = {
  element_id: string;
  element: string;
  supporting_facts: string[];
  opposing_facts: string[];
  authority_ids: string[];
  pack_item_ids: string[];
  missing_evidence: string[];
  verification_status: string;
};

export type ReasoningPackIssue = {
  issue_id: string;
  issue: string;
  legal_area: string;
  elements: ReasoningPackElement[];
  authority_ids: string[];
  facts_supporting: string[];
  facts_against: string[];
  missing_evidence: string[];
  confidence: number;
  verification_status: string;
};

export type ReasoningPackFactMapping = {
  issue_id: string;
  fact: string;
  legal_question: string;
  authority_id: string | null;
  specific_section: string;
  supporting_reasoning: string;
  risk: string;
  missing_documents: string[];
  pack_item_ids: string[];
  verification_status: string;
  lawyer_verification_required: boolean;
};

export type ReasoningPackArgument = {
  issue_id: string;
  issue: string;
  facts_relied_on: string[];
  client_argument: string;
  opposing_argument: string;
  rebuttal: string;
  weaknesses: string[];
  missing_evidence: string[];
  strength: string;
  confidence: number;
  requires_lawyer_verification: boolean;
  pack_item_ids: string[];
};

export type PreliminaryLegalOpinion = {
  matter: string;
  instructions: string;
  important_qualification: string;
  assumed_facts: string[];
  documents_reviewed: string[];
  issues: string[];
  applicable_law: string[];
  analysis: string;
  preliminary_opinion: string;
  risks: string[];
  recommended_next_steps: string[];
  conclusion: string;
  lawyer_verification_required: boolean;
};

export type LawyerReviewPack = {
  one_page_case_summary: string;
  issue_matrix_ids: string[];
  authority_ids: string[];
  missing_documents: string[];
  questions_for_client: string[];
  questions_for_lawyer: string[];
  review_notes: string[];
};

export type ReasoningPack = {
  schema_version: string;
  output_type: string;
  authority_verifications: ReasoningPackAuthority[];
  issue_matrix: ReasoningPackIssue[];
  fact_to_law_mappings: ReasoningPackFactMapping[];
  for_against_brief: ReasoningPackArgument[];
  missing_evidence_checklist: string[];
  preliminary_legal_opinion: PreliminaryLegalOpinion;
  lawyer_review_pack: LawyerReviewPack;
  lawyer_verification_required: boolean;
  warnings: string[];
};

export type AgentToolTrace = {
  schema_version: string;
  trace_id: string;
  tool_name: string;
  purpose: string;
  source_boundary: string;
  input_summary: Record<string, unknown>;
  result_count?: number | null;
  status: string;
  selected_outputs: Record<string, unknown>[];
  reviewer_note: string;
};

export type AuthorityExpansionCandidate = {
  schema_version: string;
  candidate_id: string;
  title: string;
  authority_type: string;
  citation_or_identifier: string;
  source_boundary: string;
  originating_tool_trace_id: string;
  source_hint: string;
  status: string;
  verification_status: string;
  promoted_pack_item_ids: string[];
  reviewer_note: string;
};

export type ClarificationNeed = {
  clarification_id: string;
  category: string;
  question: string;
  reason: string;
  blocks_preliminary_opinion: boolean;
};

export type AgenticResearchPlan = {
  schema_version: string;
  plan_id: string;
  matter_id: string;
  requested_output: string;
  tool_traces: AgentToolTrace[];
  clarification_needs: ClarificationNeed[];
  authority_candidates: AuthorityExpansionCandidate[];
  reviewer_summary: string;
};

export type MatterMemory = {
  schema_version: string;
  matter_id: string;
  case_id?: string | null;
  client_position?: string | null;
  selected_authority_ids: string[];
  sealed_pack_ids: string[];
  candidate_authorities: AuthorityExpansionCandidate[];
  client_facts: string[];
  adverse_material: string[];
  missing_evidence_tasks: string[];
  clarification_needs: ClarificationNeed[];
  tool_traces: AgentToolTrace[];
  review_state: Record<string, unknown>;
};

export type PackExpansionRequest = {
  query: string;
  query_class: string;
  filters: {
    require_official?: boolean;
    document_types?: string[];
    authority_levels?: number[];
    [key: string]: unknown;
  };
  max_pack_items: number;
  max_pack_tokens: number;
  case_id?: string | null;
  source_thread_id?: string | null;
  source_agent_run_id?: string | null;
  purpose: string;
};

export type AuthorityPackExpansionExecutionRecord = {
  schema_version: string;
  request_index: number;
  child_pack_id: string;
  child_pack_hash: string;
  item_count: number;
  executed_by_user_id?: string | null;
  executed_at: string;
  request_query_sha256: string;
};

export type AuthorityPackExpansionReservationRecord = {
  schema_version: string;
  reservation_id: string;
  request_index: number;
  status: string;
  reserved_by_user_id?: string | null;
  reserved_at: string;
  request_query_sha256: string;
  child_pack_id?: string | null;
  error_message?: string | null;
};

export type AuthorityPackItemVerification = {
  schema_version: string;
  child_pack_id: string;
  pack_item_id: string;
  document_id: string;
  title: string;
  document_type: string;
  source_id: string;
  authority_level: number;
  citation: string;
  anchor_status: string;
  anchor_count: number;
  page_text_available: boolean;
  source_url?: string | null;
  verification_status: string;
  requires_lawyer_review: boolean;
  issues: string[];
  citable: boolean;
  reviewer_note: string;
};

export type AuthorityPackVerificationRecord = {
  schema_version: string;
  plan_id: string;
  request_index: number;
  child_pack_id: string;
  child_pack_hash: string;
  item_count: number;
  verified_item_count: number;
  needs_review_item_count: number;
  status: string;
  verified_by_user_id?: string | null;
  verified_at: string;
  items: AuthorityPackItemVerification[];
  citable: boolean;
  promotion_boundary: string;
  reviewer_note: string;
};

export type AuthorityPackExpansionPlan = {
  schema_version: string;
  plan_id: string;
  case_id: string;
  draft_id: string;
  review_item_id: string;
  parent_pack_id: string;
  source: string;
  status: string;
  candidate_ids: string[];
  expansion_requests: PackExpansionRequest[];
  reservation_records: AuthorityPackExpansionReservationRecord[];
  executed_pack_ids: string[];
  execution_records: AuthorityPackExpansionExecutionRecord[];
  verification_records: AuthorityPackVerificationRecord[];
  citable: boolean;
  reviewer_note: string;
};

export type DraftSummary = {
  draftId: string;
  title: string;
  draftType: string;
  requestedOutput?: string | null;
  status: string;
  reviewStatus: ReviewStatus | null;
  contentPreview: string;
  claimCount: number;
  reasoningPack?: ReasoningPack | null;
  agenticResearchPlan?: AgenticResearchPlan | null;
  matterMemory?: MatterMemory | null;
  authorityPackExpansionPlans?: AuthorityPackExpansionPlan[];
};

export type ReviewItem = {
  reviewItemId: string;
  itemType: string;
  itemTitle: string;
  status: ReviewStatus;
  priority: string;
};

export type ReviewDecisionInput = {
  caseId: string;
  reviewItemId: string;
  decision: Exclude<ReviewStatus, "pending">;
  comment?: string;
};

export type WorkspaceSnapshot = {
  activeCaseId: string | null;
  projects: WorkspaceProject[];
  cases: WorkspaceCase[];
  messages: ChatMessage[];
  documents: CaseDocument[];
  researchPackItems: ResearchPackItem[];
  drafts: DraftSummary[];
  reviewItems: ReviewItem[];
};

export type WorkspaceActionResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string };

export type CreateCaseInput = {
  title: string;
  projectId?: string | null;
  projectName?: string | null;
  caseNumber?: string | null;
  court?: string | null;
  matterType?: string | null;
};

export type CreateCaseResult = {
  caseId: string;
  projectId: string;
};

export const emptyWorkspaceSnapshot: WorkspaceSnapshot = {
  activeCaseId: null,
  projects: [],
  cases: [],
  messages: [],
  documents: [],
  researchPackItems: [],
  drafts: [],
  reviewItems: [],
};
