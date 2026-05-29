"use server";

import { revalidatePath } from "next/cache";
import {
  createWorkspaceCase,
  executeAuthorityExpansionRequest,
  promoteAuthorityExpansionChildPack,
  recordWorkspaceReviewDecision,
  sendWorkspaceMessage,
  verifyAuthorityExpansionChildPack,
} from "@/lib/workspace-api";
import type {
  AuthorityExpansionExecuteInput,
  AuthorityExpansionPromoteInput,
  AuthorityExpansionVerifyInput,
  AuthorityPackExpansionExecutionResponse,
  AuthorityPackPromotionResponse,
  AuthorityPackVerificationRecord,
  ChatMessageCreateResult,
  CreateCaseInput,
  CreateCaseResult,
  ReviewDecisionInput,
  ReviewItem,
  WorkspaceActionResult,
} from "@/lib/workspace-types";

export async function createCaseAction(input: CreateCaseInput): Promise<WorkspaceActionResult<CreateCaseResult>> {
  const result = await createWorkspaceCase(input);
  if (result.ok) {
    revalidatePath("/");
  }
  return result;
}

export async function sendMessageAction(input: {
  caseId: string;
  content: string;
  threadId?: string | null;
}): Promise<WorkspaceActionResult<ChatMessageCreateResult>> {
  const result = await sendWorkspaceMessage(input);
  if (result.ok) {
    revalidatePath("/");
  }
  return result;
}

export async function recordReviewDecisionAction(input: ReviewDecisionInput): Promise<WorkspaceActionResult<ReviewItem>> {
  const result = await recordWorkspaceReviewDecision(input);
  if (result.ok) {
    revalidatePath("/");
  }
  return result;
}

export async function executeAuthorityExpansionAction(
  input: AuthorityExpansionExecuteInput,
): Promise<WorkspaceActionResult<AuthorityPackExpansionExecutionResponse>> {
  const result = await executeAuthorityExpansionRequest(input);
  if (result.ok) {
    revalidatePath("/");
  }
  return result;
}

export async function verifyAuthorityExpansionAction(
  input: AuthorityExpansionVerifyInput,
): Promise<WorkspaceActionResult<AuthorityPackVerificationRecord>> {
  const result = await verifyAuthorityExpansionChildPack(input);
  if (result.ok) {
    revalidatePath("/");
  }
  return result;
}

export async function promoteAuthorityExpansionAction(
  input: AuthorityExpansionPromoteInput,
): Promise<WorkspaceActionResult<AuthorityPackPromotionResponse>> {
  const result = await promoteAuthorityExpansionChildPack(input);
  if (result.ok) {
    revalidatePath("/");
  }
  return result;
}
