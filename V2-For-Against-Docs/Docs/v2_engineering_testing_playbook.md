# V2 Engineering and Testing Playbook

## Purpose

This playbook defines how V2 work is built, tested, documented, and released. V2 must be production ready: every feature needs typed contracts, traceable persistence, automated tests, load evidence where relevant, and documentation.

## Engineering Rules

- Keep V2 changes inside `V2-For-Against-Docs`.
- Preserve V1 as a baseline.
- Treat the database as shared and protected until a migration plan is reviewed.
- Keep legal reasoning pack-bounded and citation-first.
- Treat adverse evidence as a required output, not an optional note.
- Store all legal conclusions as reviewable objects with source traceability.
- Keep generated data, logs, local caches, and real env files out of Git.

## Test Layers

### Unit Tests

Coverage target:

- Pydantic models.
- Evidence stance validation.
- Citation role mapping.
- Prompt construction.
- Policy checks.
- Claim and counterargument validators.
- Exact citation utilities.
- Retrieval scoring helpers.
- UI pure components and state helpers.

Required examples:

- One pack item supports one claim and contradicts another.
- Mixed evidence requires a rationale.
- Out-of-pack support citation is rejected.
- Out-of-pack adverse citation is rejected.
- Uncited legal sentence is rejected.
- Prompt injection in case facts is blocked.

### Integration Tests

Coverage target:

- Repository persistence.
- PostgreSQL schema compatibility.
- API auth and case permission checks.
- Research pack creation and expansion.
- Evidence assessment persistence.
- Source viewer anchors.
- Draft and review queue persistence.
- Audit event writes.

Required examples:

- Persist a strategy draft with support, adverse, mixed, and context evidence.
- List claim details grouped by stance.
- Review an adverse evidence item and confirm audit trail.
- Retrieve source text for a cited pack item with permission.
- Reject source access without permission.

### Retrieval Evaluation

Coverage target:

- Supportive recall.
- Adverse recall.
- Mixed authority detection.
- Exact citation recall.
- Page anchor confidence.
- Source quality warning propagation.

Required reports:

- Tuned benchmark report.
- Blind benchmark report.
- Regression report by legal domain.
- Missing-source report.
- Corpus searchability report.

### End-to-End Tests

Coverage target:

- Create or open a matter.
- Submit case facts.
- Generate structured case issues.
- Retrieve research pack.
- Generate strategy memo.
- Inspect support/adverse/mixed evidence.
- Open source viewer from a cited claim.
- Approve, reject, or request changes on review items.

Required UI states:

- Empty case.
- Loading retrieval.
- Retrieval failure.
- Empty adverse evidence.
- Mixed evidence.
- Missing source warning.
- OCR or translation warning.
- Review decision success and failure.

### Load Tests

Coverage target:

- Research pack creation.
- Pack expansion.
- Strategy validation.
- Source viewer.
- Review queue.
- Workspace snapshot.

Initial load targets:

- 20 concurrent workspace users.
- 10 concurrent retrieval requests.
- 5 concurrent strategy validation requests.
- Source viewer burst of 50 requests per minute.
- No unbounded memory growth during repeated source-viewer calls.

Metrics to capture:

- p50, p95, p99 latency.
- Error rate.
- Timeout count.
- DB connection pool usage.
- OpenSearch and Qdrant latency.
- Token usage.
- Pack item count and token count.
- Citation validation failures.
- Adverse recall on benchmark cases.

## Detached Test Execution

Long-running tests, quality gates, load tests, and E2E suites must run in their own process with a PID file and log file. Use:

```bash
scripts/run_detached_quality_gate.sh full
scripts/run_detached_quality_gate.sh backend
scripts/run_detached_quality_gate.sh frontend
scripts/run_detached_quality_gate.sh tests
```

The script writes:

- PID file: `logs/test-runs/<run-id>.pid`
- Log file: `logs/test-runs/<run-id>.log`

Check progress:

```bash
tail -f logs/test-runs/<run-id>.log
```

Check process:

```bash
ps -p "$(cat logs/test-runs/<run-id>.pid)"
```

This keeps interactive chat clear while tests run under a separate PID.

## Quality Gates

Backend local gate:

```bash
PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with pydantic-settings --with fastapi --with pytest --with httpx --with eval-type-backport python scripts/run_quality_checks.py
```

Frontend local gate:

```bash
npm --prefix web run quality
```

Production release gate:

```bash
scripts/run_detached_quality_gate.sh full
```

The release gate must include:

- Python compile check.
- Secret scan.
- Unfinished-marker scan.
- Schema check.
- Rollback-only schema smoke test.
- RAG production health check.
- Backend test suite.
- Frontend lint.
- Frontend unit tests.
- Frontend build.
- Frontend dependency audit.

## Documentation Requirements

Every production feature must include:

- User behavior description.
- API contract or UI contract.
- Data model or persistence notes.
- Failure modes.
- Test coverage.
- Operational notes.
- Security and privacy considerations.

Docs live in `Docs/`. Code-facing module notes live near the code when they explain local design decisions.

## Release Checklist

- Roadmap item mapped to implementation.
- Unit tests added or updated.
- Integration tests added or updated.
- E2E coverage added for user-visible workflow.
- Load scenario added for high-traffic path.
- API docs updated.
- Codebase map updated when structure changes.
- Secret scan passed.
- Detached full quality gate passed.
- Release notes written.
- Data migrations reviewed separately before execution.
