#!/usr/bin/env node

import { createHash, createHmac } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(SCRIPT_DIR, "../..");
const DEFAULT_SECRET = "phase29-local-validation-secret-000000";
const DEFAULT_USER_ID = "phase29-lawyer";

const args = parseArgs(process.argv.slice(2));
const outputDir = path.resolve(ROOT_DIR, args.outputDir ?? "logs/phase29-browser-workflow");
const appPort = Number(args.appPort ?? (await freePort()));
const apiPort = Number(args.apiPort ?? (await freePort()));
const chromeBin = args.chromeBin ?? process.env.CHROME_BIN ?? defaultChromeBinary();

if (!chromeBin) {
  throw new Error("No Chrome binary found. Set CHROME_BIN to run the Phase 29 browser workflow validation.");
}

await mkdir(outputDir, { recursive: true });

const fixture = createFixtureState();
const apiRequests = [];
const server = createFakeBackend({
  fixture,
  apiRequests,
  secret: DEFAULT_SECRET,
  userId: DEFAULT_USER_ID,
});
await listen(server, apiPort);

const nextProcess = spawn("npm", ["--prefix", "web", "run", "dev", "--", "--hostname", "127.0.0.1", "--port", String(appPort)], {
  cwd: ROOT_DIR,
  env: {
    ...process.env,
    SL_LEGAL_API_BASE_URL: `http://127.0.0.1:${apiPort}`,
    SL_LEGAL_AUTH_HMAC_SECRET: DEFAULT_SECRET,
    SL_LEGAL_UI_SESSION_SECRET: DEFAULT_SECRET,
    SL_LEGAL_UI_USER_ID: DEFAULT_USER_ID,
  },
  stdio: ["ignore", "pipe", "pipe"],
});

const nextLogs = [];
nextProcess.stdout.on("data", (chunk) => nextLogs.push(chunk.toString()));
nextProcess.stderr.on("data", (chunk) => nextLogs.push(chunk.toString()));

const report = {
  phase: "phase29_browser_workflow_validation",
  status: "failed",
  app_url: `http://127.0.0.1:${appPort}/?caseId=case_1`,
  fake_api_url: `http://127.0.0.1:${apiPort}`,
  chrome_binary: chromeBin,
  output_dir: outputDir,
  screenshot_path: null,
  console_messages: [],
  api_requests: apiRequests,
  checks: [],
  error: null,
};

try {
  await waitForUrl(`http://127.0.0.1:${appPort}/?caseId=case_1`, 45_000);
  await runBrowserWorkflow({ report, chromeBin, appPort, outputDir });
  assertApiWorkflow(apiRequests);
  assertNoHydrationMismatch(report.console_messages);
  report.status = "passed";
  report.checks.push("Browser rendered representative matter.");
  report.checks.push("Authority workflow completed Execute -> Verify -> Promote.");
  report.checks.push("Fake backend observed signed execute, verify, and promote calls.");
  report.checks.push("No React hydration mismatch was observed with extensions disabled.");
} catch (error) {
  report.error = error instanceof Error ? error.message : "Unknown Phase 29 browser workflow error.";
} finally {
  nextProcess.kill("SIGTERM");
  await closeServer(server);
}

await writeEvidence(report, nextLogs);
if (report.status !== "passed") {
  process.exitCode = 1;
}

console.log(JSON.stringify(report, null, 2));

async function runBrowserWorkflow({ report, chromeBin, appPort, outputDir }) {
  const browser = await chromium.launch({
    executablePath: chromeBin,
    headless: true,
    args: [
      "--disable-extensions",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-sync",
      "--disable-dev-shm-usage",
    ],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.on("console", (message) => {
    report.console_messages.push({
      type: message.type(),
      text: message.text(),
    });
  });
  page.on("pageerror", (error) => {
    report.console_messages.push({
      type: "pageerror",
      text: error.message,
    });
  });

  try {
    await page.goto(`http://127.0.0.1:${appPort}/?caseId=case_1`, { waitUntil: "networkidle" });
    await page.locator('nav[aria-label="Projects and cases"]').getByText("Union Refusal Matter").waitFor({ timeout: 15_000 });
    await page.locator('aside[aria-label="Source inspector"]').getByRole("button", { name: "Reasoning" }).click();
    await page.getByRole("region", { name: "Authority expansion plans" }).waitFor({ timeout: 15_000 });
    await page.getByText("authplan_1").waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: "Execute" }).click();
    await page.getByText("Created child pack pack_child_1.").waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: "Verify" }).click();
    await page.getByText("Verified 1 authority items in pack_child_1.").waitFor({ timeout: 15_000 });
    await page.getByRole("button", { name: "Promote" }).click();
    await page.getByText("Promoted 1 authority items.").waitFor({ timeout: 15_000 });
    await page.getByText("authpromote_1").waitFor({ timeout: 15_000 });

    const screenshotPath = path.join(outputDir, "phase29-authority-workflow.png");
    await page.screenshot({ path: screenshotPath, fullPage: true });
    report.screenshot_path = screenshotPath;
  } finally {
    await browser.close();
  }
}

function createFakeBackend({ fixture, apiRequests, secret, userId }) {
  return http.createServer(async (request, response) => {
    const body = await readBody(request);
    const requestRecord = {
      method: request.method,
      url: request.url,
      signed: verifySignature({ request, body, secret, userId }),
      body: body ? JSON.parse(body) : null,
    };
    apiRequests.push(requestRecord);

    try {
      routeFakeBackend({ request, response, body, fixture });
    } catch (error) {
      json(response, 500, { detail: error instanceof Error ? error.message : "Fake backend error." });
    }
  });
}

function routeFakeBackend({ request, response, body, fixture }) {
  const method = request.method ?? "GET";
  const url = new URL(request.url ?? "/", "http://127.0.0.1");

  if (method === "GET" && url.pathname === "/v1/ui/cases/case_1/workspace") {
    json(response, 200, fixture.snapshot());
    return;
  }

  if (
    method === "POST" &&
    url.pathname === "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/requests/0/execute"
  ) {
    fixture.execute();
    json(response, 200, {
      case_id: "case_1",
      draft_id: "draft_1",
      plan_id: "authplan_1",
      request_index: 0,
      status: "executed",
      parent_pack_id: "pack_1",
      child_pack_id: "pack_child_1",
      item_count: 1,
      pack_hash: "hash_child_1",
      authority_pack_expansion_plan: fixture.plan(),
    });
    return;
  }

  if (
    method === "POST" &&
    url.pathname === "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/child-packs/pack_child_1/verify"
  ) {
    fixture.verify();
    json(response, 200, fixture.verificationRecord());
    return;
  }

  if (
    method === "POST" &&
    url.pathname === "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/child-packs/pack_child_1/promote"
  ) {
    const parsed = body ? JSON.parse(body) : {};
    if (!Array.isArray(parsed.pack_item_ids) || parsed.pack_item_ids[0] !== "pack_1_item_001") {
      json(response, 400, { detail: "Expected promotion of verified pack item pack_1_item_001." });
      return;
    }
    fixture.promote();
    json(response, 200, {
      case_id: "case_1",
      draft_id: "draft_1",
      plan_id: "authplan_1",
      child_pack_id: "pack_child_1",
      promotion_record: fixture.promotionRecord(),
      authority_pack_expansion_plan: fixture.plan(),
    });
    return;
  }

  json(response, 404, { detail: `No fake backend route for ${method} ${url.pathname}` });
}

function createFixtureState() {
  const state = {
    executed: false,
    verified: false,
    promoted: false,
  };
  return {
    execute() {
      state.executed = true;
    },
    verify() {
      state.executed = true;
      state.verified = true;
    },
    promote() {
      state.executed = true;
      state.verified = true;
      state.promoted = true;
    },
    executionRecord() {
      return {
        schema_version: "authority_pack_expansion_execution.v1",
        request_index: 0,
        child_pack_id: "pack_child_1",
        child_pack_hash: "hash_child_1",
        item_count: 1,
        executed_by_user_id: DEFAULT_USER_ID,
        executed_at: "2026-05-30T10:00:00Z",
        request_query_sha256: "a".repeat(64),
      };
    },
    verificationRecord() {
      return {
        schema_version: "authority_pack_verification.v1",
        plan_id: "authplan_1",
        request_index: 0,
        child_pack_id: "pack_child_1",
        child_pack_hash: "hash_child_1",
        item_count: 1,
        verified_item_count: 1,
        needs_review_item_count: 0,
        status: "verified",
        verified_by_user_id: DEFAULT_USER_ID,
        verified_at: "2026-05-30T10:05:00Z",
        items: [
          {
            schema_version: "authority_pack_item_verification.v1",
            child_pack_id: "pack_child_1",
            pack_item_id: "pack_1_item_001",
            document_id: "doc_1",
            title: "Industrial Disputes Act",
            document_type: "Act",
            source_id: "PARL_ACTS",
            authority_level: 2,
            citation: "Industrial Disputes Act s 1",
            anchor_status: "anchored",
            anchor_count: 1,
            page_text_available: true,
            verification_status: "verified",
            requires_lawyer_review: false,
            issues: [],
            citable: false,
            reviewer_note: "Anchored authority candidate; still non-citable until controlled promotion.",
          },
        ],
        citable: false,
        promotion_boundary: "verification_only_not_promoted",
        reviewer_note: "Child pack verified for source anchoring only.",
      };
    },
    promotionRecord() {
      return {
        schema_version: "authority_pack_promotion.v1",
        promotion_id: "authpromote_1",
        plan_id: "authplan_1",
        request_index: 0,
        child_pack_id: "pack_child_1",
        child_pack_hash: "hash_child_1",
        promoted_pack_item_ids: ["pack_1_item_001"],
        promoted_item_count: 1,
        promoted_by_user_id: DEFAULT_USER_ID,
        promoted_at: "2026-05-30T10:10:00Z",
        approval_basis: "verified_child_pack",
        citable: true,
        items: [
          {
            schema_version: "authority_pack_promotion_item.v1",
            child_pack_id: "pack_child_1",
            pack_item_id: "pack_1_item_001",
            document_id: "doc_1",
            title: "Industrial Disputes Act",
            document_type: "Act",
            source_id: "PARL_ACTS",
            authority_level: 2,
            citation: "Industrial Disputes Act s 1",
            anchor_count: 1,
            citable: true,
          },
        ],
        reviewer_note: "Promote verified authority items into matter memory for lawyer-approved citation use.",
      };
    },
    plan() {
      return {
        schema_version: "authority_pack_expansion_plan.v1",
        plan_id: "authplan_1",
        case_id: "case_1",
        draft_id: "draft_1",
        review_item_id: "review_4",
        parent_pack_id: "pack_1",
        source: "approved_authority_candidate_review",
        status: state.executed ? "executed" : "planned",
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
        reservation_records: [],
        executed_pack_ids: state.executed ? ["pack_child_1"] : [],
        execution_records: state.executed ? [this.executionRecord()] : [],
        verification_records: state.verified ? [this.verificationRecord()] : [],
        promotion_records: state.promoted ? [this.promotionRecord()] : [],
        citable: state.promoted,
        reviewer_note:
          "Planned expansion only; candidate authorities remain non-citable until retrieved, anchored, verified, and sealed into a research pack.",
      };
    },
    snapshot() {
      return {
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
            anchors: [{ anchorId: "anchor_1", pageNumber: 3, quote: "refuse to bargain", confidence: 0.96 }],
          },
        ],
        drafts: [this.draft()],
        reviewItems: [
          {
            reviewItemId: "review_4",
            itemType: "authority_candidate",
            itemTitle: "Authority candidate review",
            status: "pending",
            priority: "high",
          },
        ],
      };
    },
    draft() {
      return {
        draftId: "draft_1",
        title: "Reasoning Pack",
        draftType: "lawyer_review_pack",
        requestedOutput: "lawyer_review_pack",
        status: "draft",
        reviewStatus: "pending",
        contentPreview: "The cited Act supports the argument.",
        claimCount: 1,
        reasoningPack: reasoningPack(),
        agenticResearchPlan: agenticPlan(),
        matterMemory: matterMemory(),
        authorityPackExpansionPlans: [this.plan()],
      };
    },
  };
}

function reasoningPack() {
  return {
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
  };
}

function agenticPlan() {
  return {
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
    ],
    clarification_needs: [],
    authority_candidates: [
      {
        schema_version: "authority_expansion_candidate.v1",
        candidate_id: "authcand_1",
        title: "Current Act verification",
        authority_type: "Act",
        citation_or_identifier: "Current Act verification.",
        source_boundary: "candidate_authorities",
        originating_tool_trace_id: "trace_search_database",
        source_hint: "Missing evidence task",
        status: "candidate_unverified",
        verification_status: "requires_lawyer_review",
        promoted_pack_item_ids: [],
        reviewer_note: "Candidate only; retrieve, anchor, verify, and seal before citing as law.",
      },
    ],
  };
}

function matterMemory() {
  return {
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
    clarification_needs: [],
    tool_traces: [],
    review_state: { lawyer_review_required: true },
  };
}

function assertApiWorkflow(requests) {
  const required = [
    "/v1/ui/cases/case_1/workspace",
    "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/requests/0/execute",
    "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/child-packs/pack_child_1/verify",
    "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/child-packs/pack_child_1/promote",
  ];
  for (const pathName of required) {
    if (!requests.some((request) => request.url?.startsWith(pathName))) {
      throw new Error(`Expected fake backend call was not observed: ${pathName}`);
    }
  }
  const unsigned = requests.filter((request) => !request.signed);
  if (unsigned.length > 0) {
    throw new Error(`Expected all fake backend calls to be signed; unsigned count: ${unsigned.length}`);
  }
}

function assertNoHydrationMismatch(messages) {
  const mismatch = messages.find((message) => message.text.includes("A tree hydrated but some attributes"));
  if (mismatch) {
    throw new Error(`Hydration mismatch observed in browser validation: ${mismatch.text}`);
  }
}

async function writeEvidence(report, nextLogs) {
  await writeFile(path.join(outputDir, "phase29-browser-workflow-report.json"), JSON.stringify(report, null, 2));
  await writeFile(path.join(outputDir, "phase29-next-dev.log"), nextLogs.join(""));
  await writeFile(
    path.join(outputDir, "phase29-browser-workflow-summary.md"),
    [
      "# Phase 29 Browser Workflow Validation",
      "",
      `Status: ${report.status}`,
      `App URL: ${report.app_url}`,
      `Screenshot: ${report.screenshot_path ?? "not captured"}`,
      `Error: ${report.error ?? "none"}`,
      "",
      "## Checks",
      ...report.checks.map((check) => `- ${check}`),
      "",
      "## API Calls",
      ...report.api_requests.map((request) => `- ${request.method} ${request.url} signed=${request.signed}`),
      "",
      "## Console Messages",
      ...(report.console_messages.length
        ? report.console_messages.map((message) => `- ${message.type}: ${message.text}`)
        : ["- none"]),
      "",
    ].join("\n"),
  );
}

function verifySignature({ request, body, secret, userId }) {
  const timestamp = request.headers["x-sl-legal-auth-timestamp"];
  const signature = request.headers["x-sl-legal-auth-signature"];
  const bodySha = request.headers["x-sl-legal-body-sha256"];
  const requestUser = request.headers["x-sl-legal-user-id"];
  if (!timestamp || !signature || !bodySha || requestUser !== userId) {
    return false;
  }
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  const expectedBodySha = createHash("sha256").update(body).digest("hex");
  if (bodySha !== expectedBodySha) {
    return false;
  }
  const signaturePayload = [
    request.method ?? "GET",
    url.pathname,
    url.search.slice(1),
    userId,
    String(timestamp),
    expectedBodySha,
  ].join("\n");
  const expected = createHmac("sha256", secret).update(signaturePayload).digest("hex");
  return signature === expected;
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    request.on("error", reject);
  });
}

function json(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
  });
  response.end(JSON.stringify(payload));
}

function listen(server, port) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });
}

function closeServer(server) {
  return new Promise((resolve) => server.close(resolve));
}

async function waitForUrl(url, timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until timeout.
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => {
        if (typeof address === "object" && address?.port) {
          resolve(address.port);
        } else {
          reject(new Error("Could not allocate a free port."));
        }
      });
    });
    server.on("error", reject);
  });
}

function defaultChromeBinary() {
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function parseArgs(rawArgs) {
  const parsed = {};
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const key = arg.slice(2);
    const next = rawArgs[index + 1];
    if (next && !next.startsWith("--")) {
      parsed[toCamelCase(key)] = next;
      index += 1;
    } else {
      parsed[toCamelCase(key)] = "true";
    }
  }
  return parsed;
}

function toCamelCase(value) {
  return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}
