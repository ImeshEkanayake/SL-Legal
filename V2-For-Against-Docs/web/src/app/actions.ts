"use server";

import { revalidatePath } from "next/cache";
import {
  createWorkspaceCase,
  sendWorkspaceMessage,
} from "@/lib/workspace-api";
import type {
  ChatMessageCreateResult,
  CreateCaseInput,
  CreateCaseResult,
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
