import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CaseWorkspace } from "./CaseWorkspace";
import type { ChatMessageCreateResult, CreateCaseInput, CreateCaseResult, ReviewDecisionInput, ReviewItem, WorkspaceActionResult, WorkspaceSnapshot } from "@/lib/workspace-types";

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
      title: "Reasoning Pack",
      draftType: "lawyer_review_pack",
      requestedOutput: "lawyer_review_pack",
      status: "draft",
      reviewStatus: "pending",
      contentPreview: "The cited Act supports the argument.",
      claimCount: 1,
      reasoningPack: {
        schema_version: "reasoning_pack.v1",
        output_type: "lawyer_review_pack",
        authority_verifications: [
          {
            authority_id: "AUTH_001",
            title: "Industrial Disputes Act",
            authority_type: "Act",
            citation: "Industrial Disputes Act s 1",
            pack_item_ids: ["pack_1_item_001"],
            section: "s 1",
            official_source_checked: false,
            amendment_checked: false,
            case_law_checked: false,
            procedural_rule_checked: false,
            verification_status: "requires_lawyer_review",
            notes: "Verify current force and amendments.",
          },
        ],
        issue_matrix: [
          {
            issue_id: "ISSUE_001",
            issue: "Whether refusal to bargain is prohibited.",
            legal_area: "Labour law",
            elements: [
              {
                element_id: "ELEMENT_001",
                element: "Qualifying trade union status.",
                supporting_facts: ["The union requested bargaining."],
                opposing_facts: ["Qualification evidence is incomplete."],
                authority_ids: ["AUTH_001"],
                pack_item_ids: ["pack_1_item_001"],
                missing_evidence: ["Union registration certificate."],
                verification_status: "requires_lawyer_review",
              },
            ],
            authority_ids: ["AUTH_001"],
            facts_supporting: ["The employer refused to bargain."],
            facts_against: ["Union qualification is not yet proved."],
            missing_evidence: ["Worker representation evidence."],
            confidence: 0.55,
            verification_status: "requires_lawyer_review",
          },
        ],
        fact_to_law_mappings: [
          {
            issue_id: "ISSUE_001",
            fact: "The employer refused to bargain.",
            legal_question: "Whether the refusal engages the statutory duty.",
            authority_id: "AUTH_001",
            specific_section: "s 1",
            supporting_reasoning: "The current pack supports a preliminary argument if qualification is proven.",
            risk: "Qualification evidence is incomplete.",
            missing_documents: ["Union registration certificate."],
            pack_item_ids: ["pack_1_item_001"],
            verification_status: "requires_lawyer_review",
            lawyer_verification_required: true,
          },
        ],
        for_against_brief: [
          {
            issue_id: "ISSUE_001",
            issue: "Whether refusal to bargain is prohibited.",
            facts_relied_on: ["The employer refused to bargain."],
            client_argument: "The refusal supports the client's position if qualification is established.",
            opposing_argument: "The opposing party may argue the union was not qualifying.",
            rebuttal: "Collect registration and representation evidence.",
            weaknesses: ["Qualification evidence is incomplete."],
            missing_evidence: ["Union registration certificate."],
            strength: "medium",
            confidence: 0.55,
            requires_lawyer_verification: true,
            pack_item_ids: ["pack_1_item_001"],
          },
        ],
        missing_evidence_checklist: ["Union registration certificate.", "Current Act verification."],
        preliminary_legal_opinion: {
          matter: "Union refusal matter.",
          instructions: "Assess refusal to bargain.",
          important_qualification: "This is a preliminary lawyer-review draft requiring verification before reliance.",
          assumed_facts: ["The employer refused to bargain."],
          documents_reviewed: ["Industrial Disputes Act extract."],
          issues: ["Whether statutory refusal-to-bargain requirements are met."],
          applicable_law: ["Industrial Disputes Act s 1, subject to lawyer verification."],
          analysis: "On a preliminary basis, lawyer verification is required.",
          preliminary_opinion: "The preliminary view is that the argument may be available, subject to lawyer verification.",
          risks: ["Union qualification evidence is incomplete."],
          recommended_next_steps: ["Verify authority and collect documents."],
          conclusion: "The preliminary conclusion remains subject to lawyer verification and further evidence.",
          lawyer_verification_required: true,
        },
        lawyer_review_pack: {
          one_page_case_summary: "Employer refusal to bargain requires review against statutory elements.",
          issue_matrix_ids: ["ISSUE_001"],
          authority_ids: ["AUTH_001"],
          missing_documents: ["Union registration certificate."],
          questions_for_client: ["When was the union registered?"],
          questions_for_lawyer: ["Is the cited section current and amended?"],
          review_notes: ["Verify all authorities."],
        },
        lawyer_verification_required: true,
        warnings: ["Pack-bounded draft only."],
      },
      agenticResearchPlan: {
        schema_version: "agent_research_plan.v1",
        plan_id: "plan_1",
        matter_id: "case_1",
        requested_output: "lawyer_review_pack",
        reviewer_summary: "Agentic research plan uses sealed pack pack_1 with 1 item.",
        tool_traces: [
          {
            schema_version: "agent_tool_trace.v1",
            trace_id: "trace_search_database",
            tool_name: "search_database",
            purpose: "Use the sealed database research pack.",
            source_boundary: "database",
            input_summary: { pack_id: "pack_1" },
            result_count: 1,
            status: "completed",
            selected_outputs: [{ pack_id: "pack_1" }],
            reviewer_note: "Database retrieval is the first authority source.",
          },
          {
            schema_version: "agent_tool_trace.v1",
            trace_id: "trace_expand_authorities",
            tool_name: "expand_authorities",
            purpose: "Convert missing authority tasks into candidates.",
            source_boundary: "candidate_authorities",
            input_summary: { missing_authority_count: 1 },
            result_count: 1,
            status: "completed",
            selected_outputs: [{ authority_candidate_count: 1 }],
            reviewer_note: "Candidates are not citations until promoted.",
          },
        ],
        clarification_needs: [
          {
            clarification_id: "clarify_1",
            category: "registration_number",
            question: "What is the union registration number?",
            reason: "Registration is needed before a stronger opinion.",
            blocks_preliminary_opinion: true,
          },
        ],
        authority_candidates: [
          {
            schema_version: "authority_expansion_candidate.v1",
            candidate_id: "authcand_1",
            title: "Current Act verification",
            authority_type: "Act",
            citation_or_identifier: "Current Act verification.",
            source_boundary: "candidate_authorities",
            originating_tool_trace_id: "trace_expand_authorities",
            source_hint: "Missing evidence task",
            status: "candidate_unverified",
            verification_status: "requires_lawyer_review",
            promoted_pack_item_ids: [],
            reviewer_note: "Candidate only; retrieve, anchor, verify, and seal before citing as law.",
          },
        ],
      },
      matterMemory: {
        schema_version: "matter_memory.v1",
        matter_id: "case_1",
        case_id: "case_1",
        client_position: "union",
        selected_authority_ids: ["AUTH_001"],
        sealed_pack_ids: ["pack_1"],
        candidate_authorities: [],
        client_facts: ["The employer refused to bargain."],
        adverse_material: ["The opposing party may argue the union was not qualifying."],
        missing_evidence_tasks: ["Union registration certificate."],
        clarification_needs: [
          {
            clarification_id: "clarify_1",
            category: "registration_number",
            question: "What is the union registration number?",
            reason: "Registration is needed before a stronger opinion.",
            blocks_preliminary_opinion: true,
          },
        ],
        tool_traces: [],
        review_state: { lawyer_review_required: true },
      },
      authorityPackExpansionPlans: [
        {
          schema_version: "authority_pack_expansion_plan.v1",
          plan_id: "authplan_1",
          case_id: "case_1",
          draft_id: "draft_1",
          review_item_id: "review_4",
          parent_pack_id: "pack_1",
          source: "approved_authority_candidate_review",
          status: "planned",
          candidate_ids: ["authcand_1"],
          expansion_requests: [
            {
              query: "Current Act verification Current Act verification. Act Missing evidence task",
              query_class: "statute_lookup",
              filters: {
                require_official: true,
                authority_levels: [1, 2],
                document_types: ["statute"],
              },
              max_pack_items: 12,
              max_pack_tokens: 18000,
              case_id: "case_1",
              purpose: "authority_candidate_pack_expansion",
            },
          ],
          executed_pack_ids: [],
          execution_records: [],
          citable: false,
          reviewer_note: "Planned expansion only; candidate authorities remain non-citable until retrieved, anchored, verified, and sealed into a research pack.",
        },
      ],
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
    {
      reviewItemId: "review_2",
      itemType: "missing_evidence",
      itemTitle: "Missing evidence review",
      status: "pending",
      priority: "normal",
    },
    {
      reviewItemId: "review_3",
      itemType: "clarification_need",
      itemTitle: "Clarification review",
      status: "pending",
      priority: "high",
    },
    {
      reviewItemId: "review_4",
      itemType: "authority_candidate",
      itemTitle: "Authority candidate review",
      status: "pending",
      priority: "high",
    },
  ],
};

function renderWorkspace({
  onCreateCase,
  onSendMessage,
  onReviewDecision,
}: {
  onCreateCase?: (input: CreateCaseInput) => Promise<WorkspaceActionResult<CreateCaseResult>>;
  onSendMessage?: (input: { caseId: string; content: string; threadId?: string | null }) => Promise<WorkspaceActionResult<ChatMessageCreateResult>>;
  onReviewDecision?: (input: ReviewDecisionInput) => Promise<WorkspaceActionResult<ReviewItem>>;
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
      onReviewDecision={
        onReviewDecision ??
        vi.fn(async (input) => ({
          ok: true,
          data: {
            reviewItemId: input.reviewItemId,
            itemType: "legal_claim",
            itemTitle: "Review supported claim",
            status: input.decision,
            priority: "normal",
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

    fireEvent.click(screen.getByRole("button", { name: "Reasoning" }));
    expect(screen.getAllByRole("heading", { name: "Reasoning Pack" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Reasoning pack detail" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Agentic research workflow" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tool route and matter memory" })).toBeInTheDocument();
    expect(screen.getByText("search_database")).toBeInTheDocument();
    expect(screen.getByText("What is the union registration number?")).toBeInTheDocument();
    expect(screen.getByText("Current Act verification")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Authority expansion plans" })).toBeInTheDocument();
    expect(screen.getByText("authplan_1")).toBeInTheDocument();
    expect(screen.getByText("official required")).toBeInTheDocument();
    expect(screen.getAllByText("The opposing party may argue the union was not qualifying.").length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Preliminary opinion" })).toBeInTheDocument();
    expect(screen.getAllByText("Whether refusal to bargain is prohibited.").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Reviews" }));
    expect(screen.getAllByText("Clarification review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Authority candidate review").length).toBeGreaterThan(0);

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

  it("opens reasoning-pack citations back to the source pack item", () => {
    renderWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Reasoning" }));
    fireEvent.click(screen.getAllByRole("button", { name: /pack_1_item_001/i })[0]);

    expect(screen.getByRole("region", { name: "Research pack detail" })).toBeInTheDocument();
    expect(screen.getAllByText("Industrial Disputes Act s 1").length).toBeGreaterThan(0);
  });

  it("records review decisions from the review workspace", async () => {
    const reviewDecision = vi.fn(async (input: ReviewDecisionInput) => ({
      ok: true as const,
      data: {
        reviewItemId: input.reviewItemId,
        itemType: "legal_claim",
        itemTitle: "Review supported claim",
        status: input.decision,
        priority: "normal",
      },
    }));
    renderWorkspace({ onReviewDecision: reviewDecision });

    fireEvent.click(screen.getByRole("button", { name: "Reviews" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(reviewDecision).toHaveBeenCalledWith({
        caseId: "case_1",
        reviewItemId: "review_1",
        decision: "approved",
        comment: "",
      }),
    );
    expect(await screen.findByText("Review approved.")).toBeInTheDocument();
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
