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
