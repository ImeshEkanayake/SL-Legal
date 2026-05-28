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

export type DraftSummary = {
  draftId: string;
  title: string;
  draftType: string;
  status: string;
  reviewStatus: ReviewStatus | null;
  contentPreview: string;
  claimCount: number;
};

export type ReviewItem = {
  reviewItemId: string;
  itemType: string;
  itemTitle: string;
  status: ReviewStatus;
  priority: string;
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
