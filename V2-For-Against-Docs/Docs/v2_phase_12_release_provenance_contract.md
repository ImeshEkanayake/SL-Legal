# V2 Phase 12 Release Provenance Ledger Contract

## Scope

Phase 12 verifies release provenance for the latest completed V2 phase by linking GitHub release metadata, tag commit identity, required release documents, detached validation logs, and JSON verification evidence.

No V1 files, raw corpus data, release logs, release bundles, or database schema are committed.

## Provenance Target

The canonical provenance manifest is:

```text
rag/evals/phase12_release_provenance.json
```

Default target:

```text
repo: ImeshEkanayake/SL-Legal
release: v2-phase-11-published-asset-verification
```

## Ledger Command

Run:

```bash
PYTHONPATH=rag python3 scripts/build_phase12_release_provenance.py \
  --output logs/release-artifacts/phase12-release-provenance-ledger.json
```

Detached:

```bash
scripts/run_detached_quality_gate.sh release-provenance phase12-release-provenance
```

## Verification Rules

The ledger is `verified` only when:

- GitHub release metadata matches the expected tag;
- the release is not draft or prerelease;
- the target tag commit is resolvable and matches the remote tag commit;
- every required document exists and has a SHA-256 checksum;
- every required detached log contains `exit_status=0`;
- every required JSON status report has the expected status.

Evidence states:

- `verified`: evidence exists and matches its rule.
- `missing`: required evidence file is absent.
- `failed`: evidence exists but does not match its rule.

## Safety Boundaries

- The ledger does not upload assets.
- The ledger does not download raw corpus data.
- Generated provenance ledgers remain local evidence and are not committed to normal Git.
- A failed provenance ledger blocks treating the prior release as fully auditable.
