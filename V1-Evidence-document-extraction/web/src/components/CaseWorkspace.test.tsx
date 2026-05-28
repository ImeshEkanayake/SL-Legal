import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CaseWorkspace } from "./CaseWorkspace";
import type { ChatMessageCreateResult, CreateCaseInput, CreateCaseResult, WorkspaceActionResult, WorkspaceSnapshot } from "@/lib/workspace-types";

const routerPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

const snapshot: WorkspaceSnapshot = {
  activeCaseId: "case_1",
  projects: [{ projectId: "project_1", name: "Labour Litigation", activeCaseCount: 1 }],
  cases: [
    {
      caseId: "case_1",
      projectId: "project_1",
      title: "Union Refusal Matter",
      court: "Supreme Court",
      matterType: "fundamental_rights",
      updatedAt: "2026-05-24T00:00:00Z",
    },
  ],
  messages: [
    {
      messageId: "msg_1",
      role: "user",
      content: "Find law on refusal to bargain.",
      createdAt: "2026-05-24T00:00:00Z",
    },
    {
      messageId: "msg_2",
      role: "assistant",
      content: "The cited Act supports a lawyer-review argument. [pack_1_item_001]",
      createdAt: "2026-05-24T00:01:00Z",
      packId: "pack_1",
    },
  ],
  documents: [
    {
      documentId: "doc_1",
      title: "Industrial Disputes Act",
      documentType: "Act",
      citation: "Industrial Disputes Act s 1",
      sourceId: "PARL_ACTS",
      authorityLevel: 2,
      pageCount: 12,
      qualityFlags: [],
      textPreview: "No employer shall refuse to bargain with a qualifying trade union.",
      localPath: "data/raw/acts/industrial-disputes-act.pdf",
      sourceUrl: "https://example.test/industrial-disputes-act",
      downloadUrl: "https://example.test/industrial-disputes-act.pdf",
      caseFileAvailable: true,
      caseFileName: "doc_1_Industrial_Disputes_Act.pdf",
      viewerMimeType: "application/pdf",
    },
    {
      documentId: "doc_2",
      title: "Gazette Extraordinary 2024",
      documentType: "Gazette",
      citation: "Gazette Extraordinary No. 1",
      sourceId: "GOV_GAZETTE",
      authorityLevel: 4,
      pageCount: 3,
      qualityFlags: ["low_ocr_confidence"],
      textPreview: "",
      localPath: null,
      sourceUrl: null,
      downloadUrl: null,
      caseFileAvailable: false,
      caseFileName: null,
      viewerMimeType: null,
    },
  ],
  researchPackItems: [
    {
      packItemId: "pack_1_item_001",
      packId: "pack_1",
      documentId: "doc_1",
      citation: "Industrial Disputes Act s 1",
      title: "Industrial Disputes Act",
      authorityLevel: 2,
      fusedScore: 0.914,
      selectionReason: "exact citation; opensearch rank 1",
      sourceWarnings: [],
      anchors: [
        {
          anchorId: "anchor_1",
          pageNumber: 3,
          quote: "refuse to bargain",
          confidence: 0.96,
        },
      ],
    },
  ],
  drafts: [
    {
      draftId: "draft_1",
      title: "Strategy Report",
      draftType: "strategy_report",
      status: "draft",
      reviewStatus: "pending",
      contentPreview: "The cited Act supports the argument.",
      claimCount: 1,
    },
  ],
  reviewItems: [
    {
      reviewItemId: "review_1",
      itemType: "legal_claim",
      itemTitle: "Review supported claim",
      status: "pending",
      priority: "normal",
    },
  ],
};

function renderWorkspace({
  onCreateCase,
  onSendMessage,
}: {
  onCreateCase?: (input: CreateCaseInput) => Promise<WorkspaceActionResult<CreateCaseResult>>;
  onSendMessage?: (input: { caseId: string; content: string; threadId?: string | null }) => Promise<WorkspaceActionResult<ChatMessageCreateResult>>;
} = {}) {
  return render(
    <CaseWorkspace
      snapshot={snapshot}
      onCreateCase={
        onCreateCase ??
        vi.fn(async () => ({
          ok: true,
          data: { caseId: "case_new", projectId: "project_1" },
        }))
      }
      onSendMessage={
        onSendMessage ??
        vi.fn(async (input) => ({
          ok: true,
          data: {
            messages: [
              {
                messageId: "msg_new",
                threadId: "thread_1",
                role: "user",
                content: input.content,
                createdAt: "2026-05-24T00:02:00Z",
              },
            ],
            packId: null,
            retrievalStatus: "empty",
          },
        }))
      }
    />,
  );
}

describe("CaseWorkspace", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    routerPush.mockClear();
  });

  it("renders Codex-like legal workspace regions from a snapshot", () => {
    renderWorkspace();

    expect(screen.getByText("LegalMind AI")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Document Navigation & Chat Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /projects and cases/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /legal chat/i })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: /source inspector/i })).toBeInTheDocument();
    expect(screen.getAllByText("Union Refusal Matter").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Industrial Disputes Act").length).toBeGreaterThan(0);
  });

  it("switches the template source sidebar views with real workspace data", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    expect(screen.getByRole("heading", { name: "Document Repository" })).toBeInTheDocument();
    expect(screen.getByRole("main", { name: /case workspace/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Case files" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Active documents" })).toBeInTheDocument();
    expect(screen.getByText("Case file | 12 pages")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reviews" }));
    expect(screen.getByRole("heading", { name: "Review Queue" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Review detail" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Review queue" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review supported claim").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Drafts" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Pack" }));
    expect(screen.getByRole("heading", { name: "Research Pack" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Research pack detail" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Research pack" }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("pack_1_item_001").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Chat" }));
    expect(screen.getByRole("heading", { name: "Document Navigation & Chat Workspace" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /legal chat/i })).toBeInTheDocument();
  });

  it("uses template chat suggestions as real input actions", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Check citation anchors for this matter." }));

    expect(screen.getByLabelText("Message")).toHaveValue("Check citation anchors for this matter.");
  });

  it("opens the source document when a citation anchor is selected", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: /Page 3/i }));

    expect(screen.getAllByText("No employer shall refuse to bargain with a qualifying trade union.").length).toBeGreaterThan(0);
  });

  it("filters matters from the project rail search", () => {
    renderWorkspace();

    fireEvent.change(screen.getByLabelText("Search matters"), { target: { value: "commercial" } });

    expect(screen.getByText("No matters match the current search.")).toBeInTheDocument();
  });

  it("uses the right navigation to switch active workspace views", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Pack" }));
    expect(screen.getByRole("region", { name: "Research pack detail" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reviews" }));
    expect(screen.getByRole("region", { name: "Review detail" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    expect(screen.getByRole("heading", { name: "Case files" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Chat" }));
    expect(screen.getByRole("region", { name: /legal chat/i })).toBeInTheDocument();
  });

  it("filters documents by category and opens a case-file viewer modal", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    fireEvent.click(screen.getByRole("button", { name: /Gazettes/i }));
    expect(screen.getByRole("button", { name: /Open Gazette Extraordinary 2024/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Open Industrial Disputes Act/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /All/i }));
    fireEvent.click(screen.getByRole("button", { name: /Open Industrial Disputes Act/i }));

    expect(screen.getByRole("dialog", { name: /Industrial Disputes Act viewer/i })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Document text preview" })).toBeInTheDocument();
    expect(screen.getByText("Showing extracted case text, citation anchors, and document details.")).toBeInTheDocument();
    expect(screen.getByText("Document details")).toBeInTheDocument();
    expect(screen.getByText("Case-related extracted text")).toBeInTheDocument();
    expect(screen.getByText("Research pack anchors")).toBeInTheDocument();
    expect(screen.getAllByText("exact citation; opensearch rank 1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("refuse to bargain").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Download" })[0]).toHaveAttribute("href", "/api/cases/case_1/documents/doc_1/file");

    fireEvent.click(screen.getByRole("button", { name: "File" }));
    expect(screen.getByRole("region", { name: "Document file preview" })).toBeInTheDocument();
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
    expect(screen.getByText("Loading file")).toBeInTheDocument();
  });

  it("keeps the text viewer selectable when a document still needs OCR", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    fireEvent.click(screen.getByRole("button", { name: /Gazettes/i }));
    fireEvent.click(screen.getByRole("button", { name: /Open Gazette Extraordinary 2024/i }));
    fireEvent.click(screen.getByRole("button", { name: "Text" }));

    expect(screen.getByRole("region", { name: "Document text preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Text" })).toBeEnabled();
    expect(screen.getByText("OCR required for searchable text")).toBeInTheDocument();
  });

  it("refreshes document status through the backend-backed document status route", async () => {
    const refreshedDocument = {
      ...snapshot.documents[0],
      pageCount: 30,
      qualityFlags: [],
      textPreview: "Updated extracted text from the document status endpoint.",
    };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(refreshedDocument), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Docs" }));
    fireEvent.click(screen.getByRole("button", { name: /Open Industrial Disputes Act/i }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/cases/case_1/documents/doc_1/status"),
    );
    expect((await screen.findAllByText("Updated extracted text from the document status endpoint.")).length).toBeGreaterThan(0);
  });

  it("persists chat messages through the provided action", async () => {
    const sendMessage = vi.fn(async (input: { caseId: string; content: string; threadId?: string | null }) => ({
      ok: true as const,
      data: {
        messages: [
          {
            messageId: "msg_new",
            threadId: input.threadId ?? "thread_1",
            role: "user" as const,
            content: input.content,
            createdAt: "2026-05-24T00:02:00Z",
          },
          {
            messageId: "msg_assistant",
            threadId: input.threadId ?? "thread_1",
            role: "assistant" as const,
            content: "Found a cited pack. [pack_1_item_001]",
            createdAt: "2026-05-24T00:02:01Z",
            packId: "pack_1",
          },
        ],
        packId: "pack_1",
        retrievalStatus: "complete" as const,
      },
    }));
    renderWorkspace({ onSendMessage: sendMessage });

    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Check the latest cited source." } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    await screen.findByText("Check the latest cited source.");
    await screen.findByText("Found a cited pack. [pack_1_item_001]");
    expect(sendMessage).toHaveBeenCalledWith({
      caseId: "case_1",
      content: "Check the latest cited source.",
      threadId: null,
    });
  });

  it("opens settings and creates a matter through the action", async () => {
    const createCase = vi.fn(async () => ({
      ok: true as const,
      data: { caseId: "case_new", projectId: "project_1" },
    }));
    renderWorkspace({ onCreateCase: createCase });

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(screen.getByRole("dialog", { name: "Workspace settings" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close settings" }));

    fireEvent.click(screen.getByRole("button", { name: "New matter" }));
    fireEvent.change(screen.getByLabelText("Matter title"), { target: { value: "New Commercial Matter" } });
    fireEvent.click(screen.getByRole("button", { name: "Create matter" }));

    await waitFor(() => expect(createCase).toHaveBeenCalled());
    await waitFor(() => expect(routerPush).toHaveBeenCalledWith("/?caseId=case_new"));
  });
});
