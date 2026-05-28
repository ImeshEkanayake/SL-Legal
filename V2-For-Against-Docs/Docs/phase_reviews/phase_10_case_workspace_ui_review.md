# Phase 10 Review Packet: Case Workspace UI

## Scope

This phase adds the Codex-like case workspace under `web/` and the signed
backend workspace API that feeds it. The workspace renders project/case
navigation, persisted chat messages, document viewer, research-pack detail,
draft/review panes, source inspector, matter creation, and workspace settings
from a typed snapshot.

## Implementation Evidence

- `rag/sl_legal_rag/models.py`
  - typed workspace snapshot, message-create, and case-create API contracts.
- `rag/sl_legal_rag/db/repositories.py`
  - case workspace snapshot assembly from projects, cases, chat messages,
    case/cited documents, research pack items, anchors, drafts, and review
    items;
  - matter creation inside an existing organization/project boundary;
  - persisted user chat messages inside the active case thread.
- `rag/sl_legal_rag/api.py`
  - signed `GET /v1/ui/cases/{case_id}/workspace`;
  - signed `POST /v1/ui/cases`;
  - signed `POST /v1/ui/cases/{case_id}/messages`;
  - rate limits, body limits, RBAC checks, and audit events for UI mutations.
- `web/src/app/page.tsx`
  - server page loads a signed workspace snapshot and renders the case
    workspace.
- `web/src/app/actions.ts`
  - server actions for matter creation and chat persistence.
- `web/src/lib/workspace-types.ts`
  - typed UI contract for projects, cases, chat messages, documents, pack items,
    drafts, review items, and source anchors.
- `web/src/lib/workspace-api.ts`
  - HMAC-signed server-side API client using the same auth contract as FastAPI.
- `web/src/components/CaseWorkspace.tsx`
  - three-pane Codex-like workspace composition with navigation, modals,
    settings, chat actions, and pack-item to document synchronization.
- `web/src/components/ProjectRail.tsx`
  - project/case rail with working search, new matter action, and settings
    action.
- `web/src/components/ChatPanel.tsx`
  - chat surface with pack-boundary status, message stream, and persisted send
    action.
- `web/src/components/DocumentWorkspace.tsx`
  - working tabs for documents, research pack, drafts, and review queue.
- `web/src/components/SourceInspector.tsx`
  - pack item list, source warnings, score/authority metadata, anchor list, and
    document open action.

## Test Evidence

- `tests/test_api_research_pack_endpoint.py`
  - verifies the workspace snapshot endpoint returns the UI contract;
  - verifies signed chat message persistence;
  - verifies signed matter creation;
  - verifies workspace endpoints require signed auth.
- `tests/test_db_access_layer.py`
  - exercises repository-level workspace snapshot assembly, case creation, and
    chat persistence inside the rollback-only database workflow.
- `web/src/components/CaseWorkspace.test.tsx`
  - verifies the four main workspace regions render from typed data;
  - verifies selecting a source anchor opens the matching document text;
  - verifies matter search, tab switching, chat persistence, settings, and
    matter creation actions.
- `npm --prefix web run quality`
  - ESLint;
  - Vitest component tests;
  - production Next.js build;
  - `npm audit --audit-level=moderate`.
- Browser smoke check at `http://localhost:3007`
  - verifies chat, project search, settings, matter dialog, tab switching,
    source inspector document opening, and no horizontal overflow at desktop
    width.

## Review Notes

- The frontend avoids a landing page and opens directly into the legal
  workspace.
- The UI uses icon buttons for common actions and keeps operational text compact.
- The workspace is data-driven and uses signed server-side API access instead of
  exposing auth secrets to the browser.
- The chat composer persists user messages to the backend case thread; generated
  legal answers remain governed by the pack-bounded reasoning phase.
- Matter creation stays within the authenticated user's organization and creates
  case permissions atomically.

## Residual Production Gates

- Design review against the Codex-like reference.
- Lawyer workflow review.
- Load/performance signoff using the production corpus and realistic long chat
  threads.
