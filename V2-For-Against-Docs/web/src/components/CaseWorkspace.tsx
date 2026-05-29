"use client";

import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useMemo, useState, useTransition } from "react";
import { ChatPanel } from "./ChatPanel";
import { DocumentWorkspace, type WorkspaceTab } from "./DocumentWorkspace";
import { ProjectRail } from "./ProjectRail";
import { SourceInspector, type InspectorTab } from "./SourceInspector";
import type {
  AuthorityExpansionExecuteInput,
  AuthorityExpansionPromoteInput,
  AuthorityExpansionVerifyInput,
  AuthorityPackExpansionExecutionResponse,
  AuthorityPackExpansionPlan,
  AuthorityPackPromotionResponse,
  AuthorityPackVerificationRecord,
  ChatMessageCreateResult,
  CreateCaseInput,
  CreateCaseResult,
  DraftSummary,
  ReviewDecisionInput,
  ReviewItem,
  WorkspaceActionResult,
  WorkspaceSnapshot,
} from "@/lib/workspace-types";

type CaseWorkspaceProps = {
  snapshot: WorkspaceSnapshot;
  onCreateCase: (input: CreateCaseInput) => Promise<WorkspaceActionResult<CreateCaseResult>>;
  onSendMessage: (input: {
    caseId: string;
    content: string;
    threadId?: string | null;
  }) => Promise<WorkspaceActionResult<ChatMessageCreateResult>>;
  onReviewDecision: (input: ReviewDecisionInput) => Promise<WorkspaceActionResult<ReviewItem>>;
  onExecuteAuthorityExpansion: (input: AuthorityExpansionExecuteInput) => Promise<WorkspaceActionResult<AuthorityPackExpansionExecutionResponse>>;
  onVerifyAuthorityExpansion: (input: AuthorityExpansionVerifyInput) => Promise<WorkspaceActionResult<AuthorityPackVerificationRecord>>;
  onPromoteAuthorityExpansion: (input: AuthorityExpansionPromoteInput) => Promise<WorkspaceActionResult<AuthorityPackPromotionResponse>>;
};

export function CaseWorkspace({
  snapshot,
  onCreateCase,
  onSendMessage,
  onReviewDecision,
  onExecuteAuthorityExpansion,
  onVerifyAuthorityExpansion,
  onPromoteAuthorityExpansion,
}: CaseWorkspaceProps) {
  const router = useRouter();
  const firstDocumentId = snapshot.documents[0]?.documentId ?? null;
  const firstPackItemId = snapshot.researchPackItems[0]?.packItemId ?? null;
  const [activeCaseId, setActiveCaseId] = useState(snapshot.activeCaseId);
  const [selectedDocumentId, setSelectedDocumentId] = useState(firstDocumentId);
  const [selectedPackItemId, setSelectedPackItemId] = useState(firstPackItemId);
  const [messages, setMessages] = useState(snapshot.messages);
  const [reviewItems, setReviewItems] = useState(snapshot.reviewItems);
  const [drafts, setDrafts] = useState(snapshot.drafts);
  const [projectQuery, setProjectQuery] = useState("");
  const [newCaseOpen, setNewCaseOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>("documents");
  const [activeWorkspaceView, setActiveWorkspaceView] = useState<InspectorTab>("chat");

  const activeCase = useMemo(
    () => snapshot.cases.find((caseItem) => caseItem.caseId === activeCaseId) ?? null,
    [activeCaseId, snapshot.cases],
  );

  function selectCase(caseId: string) {
    setActiveCaseId(caseId);
    router.push(`/?caseId=${encodeURIComponent(caseId)}`);
  }

  function showWorkspaceView(view: InspectorTab) {
    setActiveWorkspaceView(view);
    if (view === "docs") {
      setWorkspaceTab("documents");
    } else if (view === "pack") {
      setWorkspaceTab("pack");
    } else if (view === "reasoning") {
      setWorkspaceTab("reasoning");
    } else if (view === "reviews") {
      setWorkspaceTab("review");
    }
  }

  function changeWorkspaceTab(tab: WorkspaceTab) {
    setWorkspaceTab(tab);
    if (tab === "documents") {
      setActiveWorkspaceView("docs");
    } else if (tab === "pack") {
      setActiveWorkspaceView("pack");
    } else if (tab === "reasoning" || tab === "drafts") {
      setActiveWorkspaceView("reasoning");
    } else if (tab === "review") {
      setActiveWorkspaceView("reviews");
    }
  }

  function selectPackItem(packItemId: string) {
    setSelectedPackItemId(packItemId);
    const packItem = snapshot.researchPackItems.find((item) => item.packItemId === packItemId);
    if (packItem) {
      setSelectedDocumentId(packItem.documentId);
    }
  }

  function openDocument(documentId: string) {
    setSelectedDocumentId(documentId);
    setWorkspaceTab("documents");
    setActiveWorkspaceView("docs");
  }

  async function submitMessage(content: string, threadId?: string | null): Promise<WorkspaceActionResult<ChatMessageCreateResult>> {
    if (!activeCaseId) {
      return { ok: false, error: "Open a matter before sending a message." };
    }
    const result = await onSendMessage({ caseId: activeCaseId, content, threadId });
    if (result.ok) {
      setMessages((current) => [...current, ...result.data.messages]);
    }
    return result;
  }

  async function recordReviewDecision(input: ReviewDecisionInput): Promise<WorkspaceActionResult<ReviewItem>> {
    const result = await onReviewDecision(input);
    if (result.ok) {
      setReviewItems((current) => current.map((item) => (item.reviewItemId === result.data.reviewItemId ? result.data : item)));
    }
    return result;
  }

  async function executeAuthorityExpansion(input: AuthorityExpansionExecuteInput): Promise<WorkspaceActionResult<AuthorityPackExpansionExecutionResponse>> {
    const result = await onExecuteAuthorityExpansion(input);
    if (result.ok) {
      replaceDraftAuthorityPlan(input.draftId, result.data.authority_pack_expansion_plan);
      router.refresh();
    }
    return result;
  }

  async function verifyAuthorityExpansion(input: AuthorityExpansionVerifyInput): Promise<WorkspaceActionResult<AuthorityPackVerificationRecord>> {
    const result = await onVerifyAuthorityExpansion(input);
    if (result.ok) {
      mergeDraftAuthorityPlanRecord(input.draftId, input.planId, "verification_records", result.data);
      router.refresh();
    }
    return result;
  }

  async function promoteAuthorityExpansion(input: AuthorityExpansionPromoteInput): Promise<WorkspaceActionResult<AuthorityPackPromotionResponse>> {
    const result = await onPromoteAuthorityExpansion(input);
    if (result.ok) {
      replaceDraftAuthorityPlan(input.draftId, result.data.authority_pack_expansion_plan);
      router.refresh();
    }
    return result;
  }

  function replaceDraftAuthorityPlan(draftId: string, plan: AuthorityPackExpansionPlan) {
    setDrafts((current) => updateDraftAuthorityPlan(current, draftId, plan));
  }

  function mergeDraftAuthorityPlanRecord(
    draftId: string,
    planId: string,
    recordKey: "verification_records" | "promotion_records",
    record: AuthorityPackVerificationRecord | AuthorityPackPromotionResponse["promotion_record"],
  ) {
    setDrafts((current) =>
      current.map((draft) => {
        if (draft.draftId !== draftId) {
          return draft;
        }
        return {
          ...draft,
          authorityPackExpansionPlans: (draft.authorityPackExpansionPlans ?? []).map((plan) =>
            plan.plan_id === planId
              ? {
                  ...plan,
                  [recordKey]: [...((plan[recordKey] as unknown[]) ?? []).filter((item) => childPackIdForRecord(item) !== childPackIdForRecord(record)), record],
                }
              : plan,
          ),
        };
      }),
    );
  }

  const workspaceHeading = workspaceViewHeading(activeWorkspaceView);
  const activeDocumentWorkspaceTab =
    activeWorkspaceView === "docs"
      ? "documents"
      : activeWorkspaceView === "pack"
        ? "pack"
        : activeWorkspaceView === "reasoning"
          ? "reasoning"
          : activeWorkspaceView === "reviews"
            ? "review"
            : workspaceTab;

  return (
    <div className="flex h-dvh min-h-dvh overflow-hidden bg-[#fcf9f5] text-[#1c1c1a]">
      <ProjectRail
        projects={snapshot.projects}
        cases={snapshot.cases}
        activeCaseId={activeCaseId}
        query={projectQuery}
        onQueryChange={setProjectQuery}
        onSelectCase={selectCase}
        onOpenNewCase={() => setNewCaseOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <div className="flex min-w-0 flex-1 overflow-hidden">
        <section className="flex min-w-0 flex-1 flex-col border-r border-[#c3c6d6] bg-[#fcf9f5]">
          <header className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-[#c3c6d6] bg-[#fcf9f5]/95 px-4">
            <div className="min-w-0">
              <h1 className="truncate text-sm font-extrabold text-[#1c1c1a]">{workspaceHeading.title}</h1>
              <p className="truncate text-xs text-[#434654]">
                {activeCase ? workspaceHeading.subtitle(activeCase.title) : "Open a matter to inspect documents, citations, drafts, and review decisions."}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {activeCase ? (
                <span className="rounded-full bg-[#f0edea] px-2.5 py-1 text-[11px] font-medium text-[#434654]">
                  {activeCase.court || activeCase.matterType || "Sri Lankan legal matter"}
                </span>
              ) : null}
              <span className="rounded-full bg-[#dae2ff] px-2.5 py-1 text-[11px] font-bold text-[#003d9b]">{reviewItems.length} review</span>
            </div>
          </header>
          <div className="min-h-0 flex-1 overflow-hidden">
            {activeWorkspaceView === "chat" ? (
              <ChatPanel activeCaseId={activeCaseId} messages={messages} onSendMessage={submitMessage} />
            ) : (
              <DocumentWorkspace
                activeCaseId={activeCaseId}
                documents={snapshot.documents}
                packItems={snapshot.researchPackItems}
                drafts={drafts}
                reviewItems={reviewItems}
                selectedDocumentId={selectedDocumentId}
                selectedPackItemId={selectedPackItemId}
                activeTab={activeDocumentWorkspaceTab}
                showTabHeader={false}
                showSummaryFooter={false}
                onActiveTabChange={changeWorkspaceTab}
                onSelectDocument={setSelectedDocumentId}
                onSelectPackItem={selectPackItem}
                onReviewDecision={recordReviewDecision}
                onExecuteAuthorityExpansion={executeAuthorityExpansion}
                onVerifyAuthorityExpansion={verifyAuthorityExpansion}
                onPromoteAuthorityExpansion={promoteAuthorityExpansion}
              />
            )}
          </div>
        </section>
        <SourceInspector
          packItems={snapshot.researchPackItems}
          documents={snapshot.documents}
          drafts={drafts}
          reviewItems={reviewItems}
          selectedPackItemId={selectedPackItemId}
          activeTab={activeWorkspaceView}
          onActiveTabChange={showWorkspaceView}
          onSelectPackItem={selectPackItem}
          onSelectDocument={openDocument}
        />
        </div>
      {newCaseOpen ? (
        <NewCaseDialog
          projects={snapshot.projects}
          onClose={() => setNewCaseOpen(false)}
          onCreateCase={onCreateCase}
          onCreated={(caseId) => {
            setNewCaseOpen(false);
            router.push(`/?caseId=${encodeURIComponent(caseId)}`);
          }}
        />
      ) : null}
      {settingsOpen ? (
        <SettingsPanel
          snapshot={snapshot}
          messageCount={messages.length}
          activeCaseTitle={activeCase?.title ?? null}
          onClose={() => setSettingsOpen(false)}
        />
      ) : null}
    </div>
  );
}

function updateDraftAuthorityPlan(drafts: DraftSummary[], draftId: string, plan: AuthorityPackExpansionPlan): DraftSummary[] {
  return drafts.map((draft) => {
    if (draft.draftId !== draftId) {
      return draft;
    }
    const plans = draft.authorityPackExpansionPlans ?? [];
    const exists = plans.some((candidate) => candidate.plan_id === plan.plan_id);
    return {
      ...draft,
      authorityPackExpansionPlans: exists
        ? plans.map((candidate) => (candidate.plan_id === plan.plan_id ? plan : candidate))
        : [...plans, plan],
    };
  });
}

function childPackIdForRecord(record: unknown): string | undefined {
  if (record && typeof record === "object" && "child_pack_id" in record) {
    return String((record as { child_pack_id?: unknown }).child_pack_id ?? "");
  }
  return undefined;
}

function NewCaseDialog({
  projects,
  onClose,
  onCreateCase,
  onCreated,
}: {
  projects: WorkspaceSnapshot["projects"];
  onClose: () => void;
  onCreateCase: (input: CreateCaseInput) => Promise<WorkspaceActionResult<CreateCaseResult>>;
  onCreated: (caseId: string) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const defaultProjectId = projects[0]?.projectId ?? "";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const projectId = String(form.get("projectId") || "");
    const projectName = String(form.get("projectName") || "");
    const input: CreateCaseInput = {
      title: String(form.get("title") || ""),
      projectId: projectId || null,
      projectName: projectId ? null : projectName,
      caseNumber: String(form.get("caseNumber") || ""),
      court: String(form.get("court") || ""),
      matterType: String(form.get("matterType") || ""),
    };
    setError(null);
    startTransition(async () => {
      const result = await onCreateCase(input);
      if (result.ok) {
        onCreated(result.data.caseId);
      } else {
        setError(result.error);
      }
    });
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/35 p-4" role="dialog" aria-modal="true" aria-labelledby="new-case-title">
      <form className="w-full max-w-lg rounded-md bg-white shadow-xl" onSubmit={submit}>
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
          <h2 id="new-case-title" className="text-sm font-semibold text-slate-950">
            New matter
          </h2>
          <button className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-slate-100" type="button" aria-label="Close new matter" onClick={onClose}>
            <X size={17} />
          </button>
        </div>
        <div className="space-y-3 p-4">
          {error ? (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800" role="alert">
              {error}
            </p>
          ) : null}
          <label className="block text-sm font-medium text-slate-800">
            Matter title
            <input className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 outline-none focus:border-slate-500" name="title" required minLength={3} />
          </label>
          {projects.length > 0 ? (
            <label className="block text-sm font-medium text-slate-800">
              Project
              <select className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 outline-none focus:border-slate-500" name="projectId" defaultValue={defaultProjectId}>
                {projects.map((project) => (
                  <option key={project.projectId} value={project.projectId}>
                    {project.name}
                  </option>
                ))}
                <option value="">Create new project</option>
              </select>
            </label>
          ) : null}
          <label className="block text-sm font-medium text-slate-800">
            New project name
            <input className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 outline-none focus:border-slate-500" name="projectName" placeholder="Required when creating a project" />
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-medium text-slate-800">
              Case number
              <input className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 outline-none focus:border-slate-500" name="caseNumber" />
            </label>
            <label className="block text-sm font-medium text-slate-800">
              Court
              <input className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 outline-none focus:border-slate-500" name="court" />
            </label>
          </div>
          <label className="block text-sm font-medium text-slate-800">
            Matter type
            <input className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 outline-none focus:border-slate-500" name="matterType" />
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 p-4">
          <button className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:bg-slate-300" type="submit" disabled={isPending}>
            Create matter
          </button>
        </div>
      </form>
    </div>
  );
}

function SettingsPanel({
  snapshot,
  messageCount,
  activeCaseTitle,
  onClose,
}: {
  snapshot: WorkspaceSnapshot;
  messageCount: number;
  activeCaseTitle: string | null;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full max-w-sm border-l border-slate-200 bg-white shadow-xl" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
        <h2 id="settings-title" className="text-sm font-semibold text-slate-950">
          Workspace settings
        </h2>
        <button className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-slate-100" type="button" aria-label="Close settings" onClick={onClose}>
          <X size={17} />
        </button>
      </div>
      <div className="space-y-4 p-4 text-sm">
        <SettingRow label="Active matter" value={activeCaseTitle ?? "None selected"} />
        <SettingRow label="Projects" value={String(snapshot.projects.length)} />
        <SettingRow label="Matters" value={String(snapshot.cases.length)} />
        <SettingRow label="Messages" value={String(messageCount)} />
        <SettingRow label="Documents" value={String(snapshot.documents.length)} />
        <SettingRow label="Pack items" value={String(snapshot.researchPackItems.length)} />
        <SettingRow label="Drafts" value={String(snapshot.drafts.length)} />
        <SettingRow label="Review items" value={String(snapshot.reviewItems.length)} />
      </div>
    </div>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-950">{value}</span>
    </div>
  );
}

function workspaceViewHeading(view: InspectorTab): { title: string; subtitle: (caseTitle: string) => string } {
  if (view === "docs") {
    return {
      title: "Document Repository",
      subtitle: (caseTitle) => `${caseTitle} | centralized legal database and research library`,
    };
  }
  if (view === "pack") {
    return {
      title: "Research Pack",
      subtitle: (caseTitle) => `${caseTitle} | cited authorities and retrieval evidence`,
    };
  }
  if (view === "reasoning") {
    return {
      title: "Reasoning Pack",
      subtitle: (caseTitle) => `${caseTitle} | preliminary opinion, missing evidence, and issue matrix`,
    };
  }
  if (view === "reviews") {
    return {
      title: "Review Queue",
      subtitle: (caseTitle) => `${caseTitle} | lawyer approval and draft checks`,
    };
  }
  return {
    title: "Document Navigation & Chat Workspace",
    subtitle: (caseTitle) => `${caseTitle} | pack-bounded chat and source review`,
  };
}
