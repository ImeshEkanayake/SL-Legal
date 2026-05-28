# V2 Phase 9 Release Artifact Contract

## Scope

Phase 9 turns release evidence into checksum reports and optional bundles that can be attached to GitHub releases or stored outside normal Git.

No V1 files, raw corpus data, evidence logs, artifact tarballs, or database schema are committed.

## Canonical Manifest

The canonical artifact manifest is:

```text
rag/evals/phase9_release_artifacts_manifest.json
```

Each artifact defines:

- `id`
- `title`
- `path`
- `required`
- `include_in_bundle`
- `evidence_scope`

Supported evidence scopes:

- `local_release`
- `production_stack`

## Artifact Report

Build the local release artifact report:

```bash
PYTHONPATH=rag python3 scripts/build_phase9_release_artifacts.py \
  --output logs/release-artifacts/phase9-artifact-report.json
```

Build the local report and tarball:

```bash
PYTHONPATH=rag python3 scripts/build_phase9_release_artifacts.py \
  --output logs/release-artifacts/phase9-artifact-report.json \
  --write-bundle
```

Build a production-stack report that records missing hosted evidence:

```bash
PYTHONPATH=rag python3 scripts/build_phase9_release_artifacts.py \
  --include-production \
  --allow-missing \
  --output logs/release-artifacts/phase9-artifact-report-production.json \
  --write-bundle \
  --bundle logs/release-artifacts/phase9-release-evidence-production.tar.gz
```

## Detached Modes

```bash
scripts/run_detached_quality_gate.sh artifact-report phase9-artifact-report
scripts/run_detached_quality_gate.sh artifact-report-production phase9-artifact-report-production
```

## Report Rules

The artifact report includes:

- artifact id and title
- path
- existence status
- byte size
- SHA-256 digest
- required-missing list
- summary counts

A local report must be `complete` before release. A production report can be `incomplete` until hosted-service evidence exists, but missing production artifacts must remain visible.

## Safety Boundaries

- Do not commit `logs/release-artifacts`.
- Do not commit tarballs.
- Do not include raw corpus data.
- Do not include `.env` files.
- Do not include `node_modules` or `.next`.
- Do not mark production artifact coverage complete when production evidence is missing.
