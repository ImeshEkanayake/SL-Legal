# V2 Phase 29 Contract: Browser Workflow Validation

## Purpose

Phase 29 provides repeatable browser evidence that the V2 authority workflow UI works end to end for a representative lawyer-review matter.

## Scope

The validation uses:

- the real Next.js workspace;
- system Chrome through Playwright Core;
- a temporary signed fake backend;
- a representative matter fixture with a reasoning pack and authority expansion plan.

It does not use the shared database, upload raw data, mutate corpus files, apply a migration, or touch V1.

## Workflow

1. Start a temporary fake backend on localhost.
2. Start the real Next app with `SL_LEGAL_API_BASE_URL` pointed at the fake backend.
3. Load `/?caseId=case_1` in headless Chrome with extensions disabled.
4. Open the reasoning workspace.
5. Click `Execute` on the authority expansion request.
6. Confirm the child pack is displayed.
7. Click `Verify` on the child pack.
8. Confirm source verification is displayed and remains non-citable.
9. Click `Promote`.
10. Confirm the promotion record is displayed as citable.

## Backend Boundary

The fake backend validates that every app request is signed with the expected HMAC headers. It records the workspace, execute, verify, and promote calls into the local report.

The promote request must contain only the verified pack item ID:

- `pack_1_item_001`

## Evidence

The runner writes local, ignored evidence under `logs/phase29-browser-workflow`:

- `phase29-browser-workflow-report.json`
- `phase29-browser-workflow-summary.md`
- `phase29-authority-workflow.png`
- `phase29-next-dev.log`

## Success Criteria

- Browser renders the representative matter.
- Browser completes Execute -> Verify -> Promote through real UI controls.
- Fake backend observes signed workspace, execute, verify, and promote calls.
- Promotion sends only the verified pack item ID.
- No React hydration mismatch is observed with extensions disabled.
- Detached backend tests and frontend quality gate remain green.
- No V1 changes, raw data upload, database migration, or raw data staging.
