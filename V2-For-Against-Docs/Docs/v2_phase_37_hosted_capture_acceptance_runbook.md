# V2 Phase 37 Runbook: Hosted Capture Acceptance Gate

## Local Gate

Run the prerequisite dry-run chain:

```bash
scripts/run_detached_quality_gate.sh backend-db-staging-validation phase37-prereq-backend-db-staging-validation
scripts/run_detached_quality_gate.sh hosted-evidence-capture-plan phase37-prereq-hosted-evidence-capture-plan
scripts/run_detached_quality_gate.sh hosted-evidence-capture-runner phase37-prereq-hosted-evidence-capture-runner
```

Then run Phase 37:

```bash
scripts/run_detached_quality_gate.sh hosted-capture-acceptance phase37-hosted-capture-acceptance
```

The expected local result is `awaiting_hosted_capture_execution`.

## Hosted Acceptance

After Phase 36 has been executed in hosted staging and Phase 34 has been rerun, execute:

```bash
scripts/run_detached_quality_gate.sh hosted-capture-acceptance phase37-hosted-capture-acceptance
```

The target status is `hosted_capture_accepted`.

## Failure Review

If the report returns `blocked`, inspect:

```text
logs/readiness/phase37-hosted-capture-acceptance.json
```

Common blockers:

- Phase 36 did not finish as `hosted_evidence_captured`.
- Phase 34 did not finish as `backend_db_staging_validated`.
- A required Phase 34 evidence file is missing.
- A detached smoke log lacks `exit_status=0`.
- A JSON evidence file has the wrong status or safety field.
- Captured evidence contains forbidden hosted-capture content.

## Safety Checklist

- Do not commit `logs/`.
- Do not paste signing headers, session cookies, DB URLs, private keys, API key labels, raw document bodies, or raw `data/` content into evidence.
- If forbidden content is found, regenerate the hosted evidence rather than editing around the problem locally.
- Keep Phase 37 as an acceptance gate; it should not execute hosted capture.
