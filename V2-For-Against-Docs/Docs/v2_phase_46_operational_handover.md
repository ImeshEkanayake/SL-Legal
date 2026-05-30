# V2 Phase 46 Operational Handover

## Support Handover

Support owns first-line operational triage after post-cutover monitoring starts.

Required support checks:

- Confirm API health and signed smoke evidence is attached.
- Confirm application error-rate evidence is within the reviewed target.
- Escalate unresolved production workflow failures to the operator owner.
- Preserve scrubbed evidence paths only; do not copy request headers, cookies, raw response bodies, DB URLs, or raw document text into handover notes.

## Legal Review Handover

Legal review owns lawyer-facing safety after cutover.

Required legal-review checks:

- Confirm lawyer review remains required for reasoning packs and preliminary opinions.
- Confirm citation validation monitoring shows no known uncited legal claims.
- Confirm source viewer smoke evidence proves citations can be traced back to source pages.
- Escalate retrieval, citation, or source-anchor regressions before relying on any generated lawyer-review pack.

## Data Update Handover

Data updates remain separate from Git code release procedures.

Required data-update checks:

- Raw data must not be committed to Git.
- Corpus growth requires a separate reviewed data plan.
- Object storage, release artifacts, Git LFS, manifests, or hydration scripts must be selected separately before any raw-data movement.
- Database migrations require their own reviewed migration plan and are not authorized by Phase 46.

## Future Corpus Growth

Future corpus growth should preserve evidence traceability and lawyer-review safety.

Required corpus-growth checks:

- Maintain source provenance, checksums, and acquisition metadata.
- Preserve page anchors, OCR quality warnings, translation status, and searchability health.
- Keep public-domain, licensed, and client-provided corpora clearly separated.
- Re-run retrieval, citation, source-viewer, and adverse-evidence evaluation before exposing new corpus material to production workflows.
