# V2 Phase 15 Release Signing Execution Plan Contract

## Scope

Phase 15 builds a non-mutating signing execution plan for the latest completed V2 release. It verifies the target release, tag commit, Phase 14 readiness report, signing artifacts, and command templates before any future signing execution is considered.

No V1 files, raw corpus data, release logs, release bundles, private signing keys, signature output files, or database schema are committed.

## Plan Target

The canonical signing plan manifest is:

```text
rag/evals/phase15_release_signing_plan.json
```

Default target:

```text
repo: ImeshEkanayake/SL-Legal
release: v2-phase-14-release-signing-readiness
```

## Plan Command

Run:

```bash
PYTHONPATH=rag python3 scripts/build_phase15_signing_plan.py \
  --output logs/release-artifacts/phase15-signing-plan.json
```

Detached:

```bash
scripts/run_detached_quality_gate.sh signing-plan phase15-signing-plan
```

## Verification Rules

The plan is `planned` only when:

- GitHub release metadata matches the expected tag;
- the release is not draft or prerelease;
- the target tag commit is resolvable and matches the remote tag commit;
- the Phase 14 readiness report exists and has status `ready_for_signing_review`;
- every required signing artifact exists and has a SHA-256 checksum;
- a supported signing mode is selected.

Supported signing modes:

- `sigstore_keyless`
- `kms_hsm`

## Execution Boundary

Phase 15 does not execute signing commands. It only records exact commands, verification commands, and expected output paths. Signing execution remains disabled unless a future reviewed phase supplies an explicit approval flag and environment plan.

## Safety Boundaries

- The signing plan does not sign artifacts.
- The signing plan does not upload assets.
- The signing plan does not download raw corpus data.
- Generated signing plans remain local evidence and are not committed to normal Git.
- A blocked signing plan prevents moving to signing execution.
