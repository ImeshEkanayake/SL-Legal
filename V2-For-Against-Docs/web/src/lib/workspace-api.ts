import "server-only";

import { createHash, createHmac } from "node:crypto";
import {
  emptyWorkspaceSnapshot,
  type AuthorityExpansionExecuteInput,
  type AuthorityExpansionPromoteInput,
  type AuthorityExpansionVerifyInput,
  type AuthorityPackExpansionExecutionResponse,
  type AuthorityPackPromotionResponse,
  type AuthorityPackVerificationRecord,
  type ChatMessageCreateResult,
  type CreateCaseInput,
  type CreateCaseResult,
  type DocumentFileResult,
  type ReviewDecisionInput,
  type ReviewItem,
  type WorkspaceActionResult,
  type WorkspaceSnapshot,
} from "./workspace-types";
import { resolveUiSession } from "./ui-session";

const USER_HEADER = "X-SL-Legal-User-ID";
const TIMESTAMP_HEADER = "X-SL-Legal-Auth-Timestamp";
const SIGNATURE_HEADER = "X-SL-Legal-Auth-Signature";
const BODY_SHA256_HEADER = "X-SL-Legal-Body-SHA256";

type LoadWorkspaceOptions = {
  caseId?: string | null;
};

type SignedFetchOptions = {
  method?: "GET" | "POST";
  json?: unknown;
};

type ApiConfig = {
  apiBaseUrl: string;
  userId: string;
  secret: string;
};

export async function loadWorkspaceSnapshot({ caseId }: LoadWorkspaceOptions): Promise<WorkspaceSnapshot> {
  if (!caseId) {
    return emptyWorkspaceSnapshot;
  }
  const response = await signedJsonFetch<WorkspaceSnapshot>(`/v1/ui/cases/${encodeURIComponent(caseId)}/workspace`);
  return response;
}

export async function createWorkspaceCase(input: CreateCaseInput): Promise<WorkspaceActionResult<CreateCaseResult>> {
  try {
    const title = input.title.trim();
    if (title.length < 3) {
      return { ok: false, error: "Matter title must be at least 3 characters." };
    }
    const projectId = input.projectId?.trim() || null;
    const projectName = input.projectName?.trim() || null;
    if (!projectId && !projectName) {
      return { ok: false, error: "Choose an existing project or enter a project name." };
    }
    const data = await signedJsonFetch<CreateCaseResult>("/v1/ui/cases", {
      method: "POST",
      json: {
        title,
        projectId,
        projectName,
        caseNumber: input.caseNumber?.trim() || null,
        court: input.court?.trim() || null,
        matterType: input.matterType?.trim() || null,
      },
    });
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: apiErrorMessage(error) };
  }
}

export async function sendWorkspaceMessage(input: {
  caseId: string;
  content: string;
  threadId?: string | null;
}): Promise<WorkspaceActionResult<ChatMessageCreateResult>> {
  try {
    const content = input.content.trim();
    if (!input.caseId) {
      return { ok: false, error: "Open a matter before sending a message." };
    }
    if (!content) {
      return { ok: false, error: "Enter a message before sending." };
    }
    const data = await signedJsonFetch<ChatMessageCreateResult>(`/v1/ui/cases/${encodeURIComponent(input.caseId)}/messages`, {
      method: "POST",
      json: {
        content,
        threadId: input.threadId || null,
      },
    });
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: apiErrorMessage(error) };
  }
}

export async function cacheWorkspaceDocumentFile(input: { caseId: string; documentId: string }): Promise<DocumentFileResult> {
  return signedJsonFetch<DocumentFileResult>(
    `/v1/ui/cases/${encodeURIComponent(input.caseId)}/documents/${encodeURIComponent(input.documentId)}/cache`,
    { method: "POST", json: {} },
  );
}

export async function recordWorkspaceReviewDecision(input: ReviewDecisionInput): Promise<WorkspaceActionResult<ReviewItem>> {
  try {
    if (!input.caseId) {
      return { ok: false, error: "Open a matter before recording review." };
    }
    if (!input.reviewItemId) {
      return { ok: false, error: "Select a review item before recording review." };
    }
    if ((input.decision === "rejected" || input.decision === "changes_requested") && !input.comment?.trim()) {
      return { ok: false, error: "Add a review comment before rejecting or requesting changes." };
    }
    const data = await signedJsonFetch<{ review_item: ReviewItem }>(
      `/v1/cases/${encodeURIComponent(input.caseId)}/review/items/${encodeURIComponent(input.reviewItemId)}/decision`,
      {
        method: "POST",
        json: {
          decision: input.decision,
          comment: input.comment?.trim() || null,
        },
      },
    );
    return { ok: true, data: data.review_item };
  } catch (error) {
    return { ok: false, error: apiErrorMessage(error) };
  }
}

export async function executeAuthorityExpansionRequest(
  input: AuthorityExpansionExecuteInput,
): Promise<WorkspaceActionResult<AuthorityPackExpansionExecutionResponse>> {
  try {
    const data = await signedJsonFetch<AuthorityPackExpansionExecutionResponse>(
      `/v1/cases/${encodeURIComponent(input.caseId)}/drafts/${encodeURIComponent(input.draftId)}/authority-expansion-plans/${encodeURIComponent(input.planId)}/requests/${input.requestIndex}/execute`,
      { method: "POST", json: {} },
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: apiErrorMessage(error) };
  }
}

export async function verifyAuthorityExpansionChildPack(
  input: AuthorityExpansionVerifyInput,
): Promise<WorkspaceActionResult<AuthorityPackVerificationRecord>> {
  try {
    const data = await signedJsonFetch<AuthorityPackVerificationRecord>(
      `/v1/cases/${encodeURIComponent(input.caseId)}/drafts/${encodeURIComponent(input.draftId)}/authority-expansion-plans/${encodeURIComponent(input.planId)}/child-packs/${encodeURIComponent(input.childPackId)}/verify`,
      { method: "POST", json: {} },
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: apiErrorMessage(error) };
  }
}

export async function promoteAuthorityExpansionChildPack(
  input: AuthorityExpansionPromoteInput,
): Promise<WorkspaceActionResult<AuthorityPackPromotionResponse>> {
  try {
    const data = await signedJsonFetch<AuthorityPackPromotionResponse>(
      `/v1/cases/${encodeURIComponent(input.caseId)}/drafts/${encodeURIComponent(input.draftId)}/authority-expansion-plans/${encodeURIComponent(input.planId)}/child-packs/${encodeURIComponent(input.childPackId)}/promote`,
      {
        method: "POST",
        json: {
          pack_item_ids: input.packItemIds ?? [],
          reviewer_note: input.reviewerNote?.trim() || "Promote verified authority items into matter memory for lawyer-approved citation use.",
        },
      },
    );
    return { ok: true, data };
  } catch (error) {
    return { ok: false, error: apiErrorMessage(error) };
  }
}

export async function signedWorkspaceFetch(path: string, options: SignedFetchOptions = {}): Promise<Response> {
  const config = await readApiConfig();
  const method = options.method ?? "GET";
  const body = options.json === undefined ? "" : JSON.stringify(options.json);
  const url = new URL(path, ensureTrailingSlash(config.apiBaseUrl));
  const bodySha256 = createHash("sha256").update(body).digest("hex");
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const signaturePayload = [method, url.pathname, url.search.slice(1), config.userId, timestamp, bodySha256].join("\n");
  const signature = createHmac("sha256", config.secret).update(signaturePayload).digest("hex");
  return fetch(url, {
    method,
    body: body ? body : undefined,
    headers: {
      Accept: "application/json, application/pdf, text/plain, application/octet-stream",
      ...(body ? { "Content-Type": "application/json" } : {}),
      [USER_HEADER]: config.userId,
      [TIMESTAMP_HEADER]: timestamp,
      [SIGNATURE_HEADER]: signature,
      [BODY_SHA256_HEADER]: bodySha256,
    },
    cache: "no-store",
  });
}

async function signedJsonFetch<T>(path: string, options: SignedFetchOptions = {}): Promise<T> {
  const response = await signedWorkspaceFetch(path, options);
  if (!response.ok) {
    throw new Error(await responseErrorText(response));
  }
  return (await response.json()) as T;
}

async function readApiConfig(): Promise<ApiConfig> {
  const apiBaseUrl = process.env.SL_LEGAL_API_BASE_URL?.trim();
  const secret = process.env.SL_LEGAL_AUTH_HMAC_SECRET?.trim();
  if (!apiBaseUrl) {
    throw new Error("SL_LEGAL_API_BASE_URL is required for case workspace data.");
  }
  if (!secret || secret.length < 32) {
    throw new Error("SL_LEGAL_AUTH_HMAC_SECRET must be at least 32 characters.");
  }
  const session = await resolveUiSession();
  const userId = session.userId;
  return { apiBaseUrl, userId, secret };
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith("/") ? value : `${value}/`;
}

async function responseErrorText(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // The status text below still gives users a recoverable, non-sensitive error.
  }
  return `Workspace API returned ${response.status} ${response.statusText}`.trim();
}

function apiErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Workspace request failed.";
}
