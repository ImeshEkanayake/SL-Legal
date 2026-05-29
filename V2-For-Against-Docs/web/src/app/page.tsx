import { CaseWorkspace } from "@/components/CaseWorkspace";
import {
  createCaseAction,
  executeAuthorityExpansionAction,
  promoteAuthorityExpansionAction,
  recordReviewDecisionAction,
  sendMessageAction,
  verifyAuthorityExpansionAction,
} from "./actions";
import { loadWorkspaceSnapshot } from "@/lib/workspace-api";

type HomeProps = {
  searchParams: Promise<{ caseId?: string }>;
};

export default async function Home({ searchParams }: HomeProps) {
  const params = await searchParams;
  const snapshot = await loadWorkspaceSnapshot({ caseId: params.caseId });
  return (
    <CaseWorkspace
      snapshot={snapshot}
      onCreateCase={createCaseAction}
      onSendMessage={sendMessageAction}
      onReviewDecision={recordReviewDecisionAction}
      onExecuteAuthorityExpansion={executeAuthorityExpansionAction}
      onVerifyAuthorityExpansion={verifyAuthorityExpansionAction}
      onPromoteAuthorityExpansion={promoteAuthorityExpansionAction}
    />
  );
}
