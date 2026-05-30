from __future__ import annotations

import json
import shlex
import statistics
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LoadScenario:
    name: str
    method: str
    path: str
    concurrency: int
    requests: int
    max_p95_ms: float
    max_error_rate: float
    body: dict[str, Any] | None = None
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class OperationalCommand:
    name: str
    section: str
    command: tuple[str, ...]
    evidence: str
    cadence: str | None = None
    requires_production_stack: bool = False
    required_for_release: bool = False
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class EvidenceRequirement:
    evidence_id: str
    title: str
    scope: str
    evidence_type: str
    path: str
    required: bool = True
    blocks_deployment: bool = True


@dataclass(frozen=True)
class ReleaseArtifact:
    artifact_id: str
    title: str
    path: str
    required: bool = True
    include_in_bundle: bool = True
    evidence_scope: str = "local_release"


@dataclass(frozen=True)
class ReleasePublicationAsset:
    asset_id: str
    title: str
    path: str
    label: str
    required: bool = True
    content_type: str = "application/octet-stream"


@dataclass(frozen=True)
class ProvenanceEvidence:
    evidence_id: str
    title: str
    path: str
    evidence_type: str
    required: bool = True
    expected_status: str | None = None


@dataclass(frozen=True)
class ReleaseAttestationSubject:
    subject_id: str
    title: str
    path: str
    subject_type: str
    required: bool = True
    expected_status: str | None = None


@dataclass(frozen=True)
class SigningReadinessEvidence:
    evidence_id: str
    title: str
    path: str
    evidence_type: str
    required: bool = True
    expected_status: str | None = None


@dataclass(frozen=True)
class SigningPlanArtifact:
    artifact_id: str
    title: str
    path: str
    label: str
    required: bool = True


def load_scenarios(path: Path) -> list[LoadScenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("load scenario file must contain a non-empty scenarios array")
    return [scenario_from_mapping(item) for item in scenarios]


def load_release_signing_plan_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase15_release_signing_plan.v1":
        raise ValueError("release signing plan manifest schema_version must be phase15_release_signing_plan.v1")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("release signing plan manifest must contain a non-empty artifacts array")
    return payload


def signing_plan_artifact_from_mapping(item: dict[str, Any]) -> SigningPlanArtifact:
    artifact_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    path = str(item.get("path") or "").strip()
    label = str(item.get("label") or Path(path).name).strip()
    if not artifact_id:
        raise ValueError("signing plan artifact id is required")
    if not title:
        raise ValueError(f"{artifact_id} title is required")
    if not path:
        raise ValueError(f"{artifact_id} path is required")
    if not label:
        raise ValueError(f"{artifact_id} label is required")
    return SigningPlanArtifact(
        artifact_id=artifact_id,
        title=title,
        path=path,
        label=label,
        required=bool(item.get("required", True)),
    )


def signing_plan_artifacts(payload: dict[str, Any]) -> list[SigningPlanArtifact]:
    return [signing_plan_artifact_from_mapping(item) for item in payload["artifacts"]]


def evaluate_signing_plan_artifact(item: SigningPlanArtifact, project_root: Path) -> dict[str, Any]:
    path = Path(item.path)
    if not path.is_absolute():
        path = project_root / path
    exists = path.is_file()
    result = {
        "id": item.artifact_id,
        "title": item.title,
        "path": item.path,
        "label": item.label,
        "required": item.required,
        "exists": exists,
        "status": "ready" if exists else "missing",
    }
    if exists:
        result["size_bytes"] = path.stat().st_size
        result["sha256"] = sha256_file(path)
    return result


def signing_command_for_artifact(mode: str, artifact: dict[str, Any], *, output_dir: str) -> dict[str, Any]:
    source = str(artifact["path"])
    signature = f"{output_dir}/{artifact['label']}.sig"
    certificate = f"{output_dir}/{artifact['label']}.crt"
    bundle = f"{output_dir}/{artifact['label']}.bundle"
    if mode == "sigstore_keyless":
        command = [
            "cosign",
            "sign-blob",
            "--yes",
            "--output-signature",
            signature,
            "--output-certificate",
            certificate,
            "--bundle",
            bundle,
            source,
        ]
        verify_command = [
            "cosign",
            "verify-blob",
            "--signature",
            signature,
            "--certificate",
            certificate,
            "--certificate-identity",
            "$SL_LEGAL_SIGNING_IDENTITY",
            "--certificate-oidc-issuer",
            "$SL_LEGAL_SIGNING_ISSUER",
            source,
        ]
    elif mode == "kms_hsm":
        command = [
            "cosign",
            "sign-blob",
            "--key",
            "$SL_LEGAL_KMS_KEY_URI",
            "--output-signature",
            signature,
            source,
        ]
        verify_command = [
            "cosign",
            "verify-blob",
            "--key",
            "$SL_LEGAL_KMS_PUBLIC_KEY_URI",
            "--signature",
            signature,
            source,
        ]
    else:
        command = []
        verify_command = []
    return {
        "artifact_id": artifact["id"],
        "mode": mode,
        "command": command,
        "command_line": " ".join(shlex.quote(part) for part in command),
        "verify_command": verify_command,
        "verify_command_line": " ".join(shlex.quote(part) for part in verify_command),
        "expected_outputs": {
            "signature": signature,
            "certificate": certificate if mode == "sigstore_keyless" else None,
            "bundle": bundle if mode == "sigstore_keyless" else None,
        },
    }


def build_release_signing_plan(
    plan_payload: dict[str, Any],
    *,
    project_root: Path,
    release_metadata: dict[str, Any],
    git_metadata: dict[str, Any],
) -> dict[str, Any]:
    target_tag = str(plan_payload.get("target_release_tag") or "").strip()
    repo = str(plan_payload.get("repo") or "").strip()
    mode = str(plan_payload.get("signing_mode") or "").strip()
    output_dir = str(plan_payload.get("signature_output_dir") or "logs/release-artifacts/signatures").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    if mode not in {"sigstore_keyless", "kms_hsm"}:
        raise ValueError(f"unsupported signing mode: {mode}")
    artifacts = [evaluate_signing_plan_artifact(item, project_root) for item in signing_plan_artifacts(plan_payload)]
    readiness_path = str(plan_payload.get("readiness_report_path") or "").strip()
    if not readiness_path:
        raise ValueError("readiness_report_path is required")
    readiness_file = Path(readiness_path)
    if not readiness_file.is_absolute():
        readiness_file = project_root / readiness_file
    readiness_exists = readiness_file.is_file()
    readiness_status = "missing"
    readiness_sha = ""
    readiness_size = None
    if readiness_exists:
        readiness_payload = json.loads(readiness_file.read_text(encoding="utf-8"))
        readiness_status = str(readiness_payload.get("status") or "")
        readiness_sha = sha256_file(readiness_file)
        readiness_size = readiness_file.stat().st_size
    release_status = (
        "verified"
        if str(release_metadata.get("tagName") or "") == target_tag
        and not bool(release_metadata.get("isDraft"))
        and not bool(release_metadata.get("isPrerelease"))
        and bool(release_metadata.get("url"))
        else "failed"
    )
    tag_commit = str(git_metadata.get("tag_commit") or "").strip()
    remote_tag_commit = str(git_metadata.get("remote_tag_commit") or "").strip()
    commit_status = "verified" if tag_commit and remote_tag_commit and tag_commit == remote_tag_commit else "failed"
    execution_approved = bool(plan_payload.get("signing_execution_approved", False))
    blockers = [item for item in artifacts if item["required"] and item["status"] != "ready"]
    if release_status != "verified":
        blockers.append({"id": "github_release", "status": release_status, "summary": "release metadata failed"})
    if commit_status != "verified":
        blockers.append({"id": "release_tag_commit", "status": commit_status, "summary": "local and remote tag commits differ"})
    if readiness_status != "ready_for_signing_review":
        blockers.append({"id": "signing_readiness", "status": readiness_status, "summary": "signing readiness report is not ready"})
    commands = [
        signing_command_for_artifact(mode, artifact, output_dir=output_dir)
        for artifact in artifacts
        if artifact["status"] == "ready"
    ]
    if blockers:
        status = "blocked"
    elif execution_approved:
        status = "execution_ready"
    else:
        status = "planned"
    return {
        "schema_version": "phase15_release_signing_plan.v1",
        "source_schema_version": plan_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "signing_mode": mode,
        "signing_execution_approved": execution_approved,
        "release": {
            "status": release_status,
            "tagName": release_metadata.get("tagName"),
            "name": release_metadata.get("name"),
            "url": release_metadata.get("url"),
            "isDraft": bool(release_metadata.get("isDraft")),
            "isPrerelease": bool(release_metadata.get("isPrerelease")),
        },
        "git": {
            "status": commit_status,
            "tag_commit": tag_commit,
            "remote_tag_commit": remote_tag_commit,
        },
        "readiness_report": {
            "path": readiness_path,
            "exists": readiness_exists,
            "status": readiness_status,
            "size_bytes": readiness_size,
            "sha256": readiness_sha,
        },
        "artifacts": artifacts,
        "commands": commands,
        "blockers": blockers,
        "summary": {
            "total_artifacts": len(artifacts),
            "ready_artifacts": sum(1 for item in artifacts if item["status"] == "ready"),
            "missing_artifacts": sum(1 for item in artifacts if item["status"] == "missing"),
            "planned_commands": len(commands),
        },
    }


def load_release_signing_readiness_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase14_release_signing_readiness.v1":
        raise ValueError("release signing readiness manifest schema_version must be phase14_release_signing_readiness.v1")
    modes = payload.get("approved_signing_modes")
    if not isinstance(modes, list) or not modes:
        raise ValueError("release signing readiness manifest must contain approved_signing_modes")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("release signing readiness manifest must contain a non-empty evidence array")
    return payload


def signing_readiness_evidence_from_mapping(item: dict[str, Any]) -> SigningReadinessEvidence:
    evidence_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    path = str(item.get("path") or "").strip()
    evidence_type = str(item.get("type") or "").strip()
    expected_status = str(item["expected_status"]).strip() if item.get("expected_status") else None
    if not evidence_id:
        raise ValueError("signing readiness evidence id is required")
    if not title:
        raise ValueError(f"{evidence_id} title is required")
    if not path:
        raise ValueError(f"{evidence_id} path is required")
    if evidence_type not in {"document", "json_status"}:
        raise ValueError(f"{evidence_id} has unsupported signing readiness evidence type: {evidence_type}")
    return SigningReadinessEvidence(
        evidence_id=evidence_id,
        title=title,
        path=path,
        evidence_type=evidence_type,
        required=bool(item.get("required", True)),
        expected_status=expected_status,
    )


def signing_readiness_evidence(payload: dict[str, Any]) -> list[SigningReadinessEvidence]:
    return [signing_readiness_evidence_from_mapping(item) for item in payload["evidence"]]


def evaluate_signing_readiness_evidence(item: SigningReadinessEvidence, project_root: Path) -> dict[str, Any]:
    path = Path(item.path)
    if not path.is_absolute():
        path = project_root / path
    base = {
        "id": item.evidence_id,
        "title": item.title,
        "path": item.path,
        "type": item.evidence_type,
        "required": item.required,
        "expected_status": item.expected_status,
        "exists": path.is_file(),
    }
    if not path.is_file():
        return {**base, "status": "missing", "summary": "signing readiness evidence is not present"}
    result = {
        **base,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if item.evidence_type == "document":
        return {**result, "status": "verified", "summary": "document present"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_status = str(payload.get("status") or payload.get("decision") or "").strip()
    matches = actual_status == item.expected_status if item.expected_status else bool(actual_status)
    return {
        **result,
        "status": "verified" if matches else "failed",
        "actual_status": actual_status,
        "summary": f"json status={actual_status}",
    }


def forbidden_signing_paths(project_root: Path, patterns: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for pattern in patterns:
        for path in sorted(project_root.glob(pattern)):
            if not path.is_file():
                continue
            try:
                relative = str(path.relative_to(project_root))
            except ValueError:
                relative = str(path)
            matches.append(
                {
                    "pattern": pattern,
                    "path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return matches


def build_release_signing_readiness_report(
    readiness_payload: dict[str, Any],
    *,
    project_root: Path,
    release_metadata: dict[str, Any],
    git_metadata: dict[str, Any],
) -> dict[str, Any]:
    target_tag = str(readiness_payload.get("target_release_tag") or "").strip()
    repo = str(readiness_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    modes = [str(item).strip() for item in readiness_payload.get("approved_signing_modes", []) if str(item).strip()]
    invalid_modes = [item for item in modes if item not in {"sigstore_keyless", "kms_hsm"}]
    evidence = [
        evaluate_signing_readiness_evidence(item, project_root)
        for item in signing_readiness_evidence(readiness_payload)
    ]
    release_status = (
        "verified"
        if str(release_metadata.get("tagName") or "") == target_tag
        and not bool(release_metadata.get("isDraft"))
        and not bool(release_metadata.get("isPrerelease"))
        and bool(release_metadata.get("url"))
        else "failed"
    )
    tag_commit = str(git_metadata.get("tag_commit") or "").strip()
    remote_tag_commit = str(git_metadata.get("remote_tag_commit") or "").strip()
    commit_status = "verified" if tag_commit and remote_tag_commit and tag_commit == remote_tag_commit else "failed"
    forbidden_patterns = [str(item) for item in readiness_payload.get("forbidden_secret_file_globs", [])]
    forbidden_matches = forbidden_signing_paths(project_root, forbidden_patterns)
    environment_requirements = readiness_payload.get("environment_requirements") or {}
    required_for_execution = [
        str(item)
        for item in environment_requirements.get("required_for_execution", [])
        if str(item).strip()
    ] if isinstance(environment_requirements, dict) else []
    signing_execution_approved = bool(readiness_payload.get("signing_execution_approved", False))
    signing_execution_enabled = signing_execution_approved and bool(required_for_execution)
    blockers = [item for item in evidence if item["required"] and item["status"] != "verified"]
    if release_status != "verified":
        blockers.append({"id": "github_release", "status": release_status, "summary": "release metadata failed"})
    if commit_status != "verified":
        blockers.append({"id": "release_tag_commit", "status": commit_status, "summary": "local and remote tag commits differ"})
    for mode in invalid_modes:
        blockers.append({"id": "approved_signing_mode", "status": "failed", "summary": f"unsupported signing mode: {mode}"})
    if forbidden_matches:
        blockers.append({"id": "forbidden_secret_files", "status": "failed", "summary": "forbidden signing secret files are present"})
    return {
        "schema_version": "phase14_release_signing_readiness_report.v1",
        "source_schema_version": readiness_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": "ready_for_signing_review" if not blockers else "blocked",
        "release": {
            "status": release_status,
            "tagName": release_metadata.get("tagName"),
            "name": release_metadata.get("name"),
            "url": release_metadata.get("url"),
            "isDraft": bool(release_metadata.get("isDraft")),
            "isPrerelease": bool(release_metadata.get("isPrerelease")),
        },
        "git": {
            "status": commit_status,
            "tag_commit": tag_commit,
            "remote_tag_commit": remote_tag_commit,
        },
        "approved_signing_modes": modes,
        "environment_requirements": {
            "required_for_execution": required_for_execution,
            "execution_enabled": signing_execution_enabled,
            "execution_approved": signing_execution_approved,
            "summary": "Signing execution is intentionally disabled until reviewed environment variables are supplied.",
        },
        "forbidden_secret_file_globs": forbidden_patterns,
        "forbidden_secret_file_matches": forbidden_matches,
        "evidence": evidence,
        "blockers": blockers,
        "summary": {
            "total_evidence": len(evidence),
            "verified_evidence": sum(1 for item in evidence if item["status"] == "verified"),
            "failed_evidence": sum(1 for item in evidence if item["status"] == "failed"),
            "missing_evidence": sum(1 for item in evidence if item["status"] == "missing"),
            "forbidden_secret_file_matches": len(forbidden_matches),
        },
    }


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_release_attestation_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase13_release_attestation.v1":
        raise ValueError("release attestation manifest schema_version must be phase13_release_attestation.v1")
    subjects = payload.get("subjects")
    if not isinstance(subjects, list) or not subjects:
        raise ValueError("release attestation manifest must contain a non-empty subjects array")
    return payload


def attestation_subject_from_mapping(item: dict[str, Any]) -> ReleaseAttestationSubject:
    subject_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    path = str(item.get("path") or "").strip()
    subject_type = str(item.get("type") or "").strip()
    expected_status = str(item["expected_status"]).strip() if item.get("expected_status") else None
    if not subject_id:
        raise ValueError("attestation subject id is required")
    if not title:
        raise ValueError(f"{subject_id} title is required")
    if not path:
        raise ValueError(f"{subject_id} path is required")
    if subject_type not in {"document", "json_status"}:
        raise ValueError(f"{subject_id} has unsupported attestation subject type: {subject_type}")
    return ReleaseAttestationSubject(
        subject_id=subject_id,
        title=title,
        path=path,
        subject_type=subject_type,
        required=bool(item.get("required", True)),
        expected_status=expected_status,
    )


def attestation_subjects(payload: dict[str, Any]) -> list[ReleaseAttestationSubject]:
    return [attestation_subject_from_mapping(item) for item in payload["subjects"]]


def evaluate_attestation_subject(item: ReleaseAttestationSubject, project_root: Path) -> dict[str, Any]:
    path = Path(item.path)
    if not path.is_absolute():
        path = project_root / path
    base = {
        "id": item.subject_id,
        "title": item.title,
        "path": item.path,
        "type": item.subject_type,
        "required": item.required,
        "expected_status": item.expected_status,
        "exists": path.is_file(),
    }
    if not path.is_file():
        return {**base, "status": "missing", "summary": "attestation subject is not present"}
    result = {
        **base,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if item.subject_type == "document":
        return {**result, "status": "verified", "summary": "document subject present"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_status = str(payload.get("status") or payload.get("decision") or "").strip()
    matches = actual_status == item.expected_status if item.expected_status else bool(actual_status)
    return {
        **result,
        "status": "verified" if matches else "failed",
        "actual_status": actual_status,
        "summary": f"json status={actual_status}",
    }


def build_release_attestation(
    attestation_payload: dict[str, Any],
    *,
    project_root: Path,
    release_metadata: dict[str, Any],
    git_metadata: dict[str, Any],
) -> dict[str, Any]:
    target_tag = str(attestation_payload.get("target_release_tag") or "").strip()
    repo = str(attestation_payload.get("repo") or "").strip()
    predicate_type = str(attestation_payload.get("predicate_type") or "").strip()
    builder_id = str(attestation_payload.get("builder_id") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    if not predicate_type:
        raise ValueError("predicate_type is required")
    if not builder_id:
        raise ValueError("builder_id is required")
    subjects = [evaluate_attestation_subject(item, project_root) for item in attestation_subjects(attestation_payload)]
    release_status = (
        "verified"
        if str(release_metadata.get("tagName") or "") == target_tag
        and not bool(release_metadata.get("isDraft"))
        and not bool(release_metadata.get("isPrerelease"))
        and bool(release_metadata.get("url"))
        else "failed"
    )
    tag_commit = str(git_metadata.get("tag_commit") or "").strip()
    remote_tag_commit = str(git_metadata.get("remote_tag_commit") or "").strip()
    commit_status = "verified" if tag_commit and remote_tag_commit and tag_commit == remote_tag_commit else "failed"
    failures = [item for item in subjects if item["required"] and item["status"] != "verified"]
    if release_status != "verified":
        failures.append({"id": "github_release", "status": release_status, "summary": "release metadata failed"})
    if commit_status != "verified":
        failures.append({"id": "release_tag_commit", "status": commit_status, "summary": "local and remote tag commits differ"})
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": predicate_type,
        "subject": [
            {
                "name": item["path"],
                "digest": {"sha256": item["sha256"]},
                "size_bytes": item["size_bytes"],
            }
            for item in subjects
            if item.get("sha256")
        ],
        "predicate": {
            "builder": {"id": builder_id},
            "buildType": "https://sl-legal.local/release-attestation/v1",
            "target": {
                "repo": repo,
                "release_tag": target_tag,
                "release_url": release_metadata.get("url"),
                "tag_commit": tag_commit,
            },
            "materials": [
                {
                    "uri": f"git+https://github.com/{repo}@{target_tag}",
                    "digest": {"sha1": tag_commit},
                }
            ],
            "verification": {
                "release_status": release_status,
                "tag_commit_status": commit_status,
                "subject_count": len(subjects),
                "verified_subject_count": sum(1 for item in subjects if item["status"] == "verified"),
            },
        },
    }
    attestation_digest = sha256_bytes(canonical_json_bytes(statement))
    return {
        "schema_version": "phase13_release_attestation.v1",
        "source_schema_version": attestation_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": "verified" if not failures else "failed",
        "attestation_digest": attestation_digest,
        "signature": {
            "type": "local-checksum-attestation",
            "algorithm": "sha256",
            "signed": False,
            "digest": attestation_digest,
        },
        "release": {
            "status": release_status,
            "tagName": release_metadata.get("tagName"),
            "name": release_metadata.get("name"),
            "url": release_metadata.get("url"),
            "isDraft": bool(release_metadata.get("isDraft")),
            "isPrerelease": bool(release_metadata.get("isPrerelease")),
        },
        "git": {
            "status": commit_status,
            "tag_commit": tag_commit,
            "remote_tag_commit": remote_tag_commit,
        },
        "subjects": subjects,
        "statement": statement,
        "failures": failures,
        "summary": {
            "total_subjects": len(subjects),
            "verified_subjects": sum(1 for item in subjects if item["status"] == "verified"),
            "failed_subjects": sum(1 for item in subjects if item["status"] == "failed"),
            "missing_subjects": sum(1 for item in subjects if item["status"] == "missing"),
        },
    }


def load_release_provenance_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase12_release_provenance.v1":
        raise ValueError("release provenance manifest schema_version must be phase12_release_provenance.v1")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("release provenance manifest must contain a non-empty evidence array")
    return payload


def provenance_evidence_from_mapping(item: dict[str, Any]) -> ProvenanceEvidence:
    evidence_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    path = str(item.get("path") or "").strip()
    evidence_type = str(item.get("type") or "").strip()
    expected_status = str(item["expected_status"]).strip() if item.get("expected_status") else None
    if not evidence_id:
        raise ValueError("provenance evidence id is required")
    if not title:
        raise ValueError(f"{evidence_id} title is required")
    if not path:
        raise ValueError(f"{evidence_id} path is required")
    if evidence_type not in {"document", "detached_log", "json_status"}:
        raise ValueError(f"{evidence_id} has unsupported provenance evidence type: {evidence_type}")
    return ProvenanceEvidence(
        evidence_id=evidence_id,
        title=title,
        path=path,
        evidence_type=evidence_type,
        required=bool(item.get("required", True)),
        expected_status=expected_status,
    )


def provenance_evidence(payload: dict[str, Any]) -> list[ProvenanceEvidence]:
    return [provenance_evidence_from_mapping(item) for item in payload["evidence"]]


def evaluate_provenance_evidence(item: ProvenanceEvidence, project_root: Path) -> dict[str, Any]:
    path = Path(item.path)
    if not path.is_absolute():
        path = project_root / path
    base = {
        "id": item.evidence_id,
        "title": item.title,
        "path": item.path,
        "type": item.evidence_type,
        "required": item.required,
        "expected_status": item.expected_status,
        "exists": path.is_file(),
    }
    if not path.is_file():
        return {**base, "status": "missing", "summary": "evidence file is not present"}
    result = {
        **base,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if item.evidence_type == "document":
        return {**result, "status": "verified", "summary": "document present"}
    if item.evidence_type == "detached_log":
        text = path.read_text(encoding="utf-8", errors="replace")
        passed = "exit_status=0" in text
        return {
            **result,
            "status": "verified" if passed else "failed",
            "summary": "detached run exited 0" if passed else "detached run did not exit 0",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_status = str(payload.get("status") or payload.get("decision") or "").strip()
    matches = actual_status == item.expected_status if item.expected_status else bool(actual_status)
    return {
        **result,
        "status": "verified" if matches else "failed",
        "actual_status": actual_status,
        "summary": f"json status={actual_status}",
    }


def build_release_provenance_ledger(
    provenance_payload: dict[str, Any],
    *,
    project_root: Path,
    git_metadata: dict[str, Any],
    release_metadata: dict[str, Any],
) -> dict[str, Any]:
    target_tag = str(provenance_payload.get("target_release_tag") or "").strip()
    repo = str(provenance_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    evidence = [evaluate_provenance_evidence(item, project_root) for item in provenance_evidence(provenance_payload)]
    release_status = (
        "verified"
        if str(release_metadata.get("tagName") or "") == target_tag
        and not bool(release_metadata.get("isDraft"))
        and not bool(release_metadata.get("isPrerelease"))
        and bool(release_metadata.get("url"))
        else "failed"
    )
    tag_commit = str(git_metadata.get("tag_commit") or "").strip()
    remote_tag_commit = str(git_metadata.get("remote_tag_commit") or "").strip()
    commit_status = "verified" if tag_commit and remote_tag_commit and tag_commit == remote_tag_commit else "failed"
    failures = [
        item for item in evidence if item["required"] and item["status"] != "verified"
    ]
    if release_status != "verified":
        failures.append({"id": "github_release", "status": release_status, "summary": "release metadata failed"})
    if commit_status != "verified":
        failures.append({"id": "release_tag_commit", "status": commit_status, "summary": "local and remote tag commits differ"})
    return {
        "schema_version": "phase12_release_provenance_ledger.v1",
        "source_schema_version": provenance_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": "verified" if not failures else "failed",
        "release": {
            "status": release_status,
            "tagName": release_metadata.get("tagName"),
            "name": release_metadata.get("name"),
            "url": release_metadata.get("url"),
            "isDraft": bool(release_metadata.get("isDraft")),
            "isPrerelease": bool(release_metadata.get("isPrerelease")),
        },
        "git": {
            "status": commit_status,
            "tag_commit": tag_commit,
            "remote_tag_commit": remote_tag_commit,
        },
        "evidence": evidence,
        "failures": failures,
        "summary": {
            "total_evidence": len(evidence),
            "verified_evidence": sum(1 for item in evidence if item["status"] == "verified"),
            "failed_evidence": sum(1 for item in evidence if item["status"] == "failed"),
            "missing_evidence": sum(1 for item in evidence if item["status"] == "missing"),
        },
    }


def load_operational_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase7_deployment_monitoring.v1":
        raise ValueError("operational manifest schema_version must be phase7_deployment_monitoring.v1")
    sections = payload.get("sections")
    if not isinstance(sections, dict) or not sections:
        raise ValueError("operational manifest must contain non-empty sections")
    return payload


def load_release_publication_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase10_release_asset_publication.v1":
        raise ValueError("publication manifest schema_version must be phase10_release_asset_publication.v1")
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("publication manifest must contain a non-empty assets array")
    return payload


def release_publication_asset_from_mapping(item: dict[str, Any]) -> ReleasePublicationAsset:
    asset_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    path = str(item.get("path") or "").strip()
    label = str(item.get("label") or "").strip()
    content_type = str(item.get("content_type") or "application/octet-stream").strip()
    if not asset_id:
        raise ValueError("publication asset id is required")
    if not title:
        raise ValueError(f"{asset_id} title is required")
    if not path:
        raise ValueError(f"{asset_id} path is required")
    if not label:
        raise ValueError(f"{asset_id} label is required")
    return ReleasePublicationAsset(
        asset_id=asset_id,
        title=title,
        path=path,
        label=label,
        required=bool(item.get("required", True)),
        content_type=content_type,
    )


def release_publication_assets(payload: dict[str, Any]) -> list[ReleasePublicationAsset]:
    return [release_publication_asset_from_mapping(item) for item in payload["assets"]]


def is_allowed_publication_path(path: str) -> bool:
    parts = Path(path).parts
    blocked_parts = {"data", "node_modules", ".next", ".git"}
    if any(part in blocked_parts for part in parts):
        return False
    if Path(path).name.startswith(".env"):
        return False
    return path.startswith("logs/release-artifacts/")


def build_release_publication_plan(
    publication_payload: dict[str, Any],
    *,
    project_root: Path,
    target_tag: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    assets = release_publication_assets(publication_payload)
    target = target_tag or str(publication_payload.get("target_release_tag") or "")
    repository = repo or str(publication_payload.get("repo") or "")
    if not target:
        raise ValueError("target release tag is required")
    if not repository:
        raise ValueError("repository is required")
    items: list[dict[str, Any]] = []
    for asset in assets:
        path = Path(asset.path)
        if not path.is_absolute():
            path = project_root / path
        allowed = is_allowed_publication_path(asset.path)
        exists = path.is_file()
        item = {
            "id": asset.asset_id,
            "title": asset.title,
            "path": asset.path,
            "label": asset.label,
            "required": asset.required,
            "content_type": asset.content_type,
            "exists": exists,
            "allowed_path": allowed,
            "status": "ready" if exists and allowed else "blocked",
        }
        if exists:
            item["size_bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
        items.append(item)
    blockers = [item for item in items if item["required"] and item["status"] != "ready"]
    return {
        "schema_version": "phase10_release_publication_plan.v1",
        "source_schema_version": publication_payload["schema_version"],
        "target_release_tag": target,
        "repo": repository,
        "status": "ready" if not blockers else "blocked",
        "assets": items,
        "blockers": blockers,
        "summary": {
            "total": len(items),
            "ready": sum(1 for item in items if item["status"] == "ready"),
            "blocked": sum(1 for item in items if item["status"] == "blocked"),
        },
    }


def normalize_release_asset_digest(value: str | None) -> str:
    digest = str(value or "").strip()
    return digest.removeprefix("sha256:")


def build_release_asset_verification_report(
    publication_payload: dict[str, Any],
    *,
    project_root: Path,
    remote_assets: list[dict[str, Any]],
    target_tag: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    plan = build_release_publication_plan(
        publication_payload,
        project_root=project_root,
        target_tag=target_tag,
        repo=repo,
    )
    remote_by_name = {str(item.get("name") or ""): item for item in remote_assets}
    verified_assets: list[dict[str, Any]] = []
    for item in plan["assets"]:
        remote = remote_by_name.get(str(item["label"]))
        if not remote:
            status = "missing_remote"
            remote_digest = ""
            remote_size = None
        else:
            remote_digest = normalize_release_asset_digest(str(remote.get("digest") or ""))
            remote_size = int(remote.get("size") or 0)
            status = (
                "verified"
                if item.get("status") == "ready"
                and item.get("sha256") == remote_digest
                and int(item.get("size_bytes") or -1) == remote_size
                else "mismatch"
            )
        verified_assets.append(
            {
                **item,
                "remote_exists": remote is not None,
                "remote_sha256": remote_digest,
                "remote_size_bytes": remote_size,
                "remote_url": remote.get("url") if remote else None,
                "verification_status": status,
            }
        )
    failures = [item for item in verified_assets if item["verification_status"] != "verified"]
    return {
        "schema_version": "phase11_release_asset_verification.v1",
        "source_schema_version": publication_payload["schema_version"],
        "target_release_tag": plan["target_release_tag"],
        "repo": plan["repo"],
        "status": "verified" if not failures else "failed",
        "assets": verified_assets,
        "failures": failures,
        "summary": {
            "total": len(verified_assets),
            "verified": sum(1 for item in verified_assets if item["verification_status"] == "verified"),
            "failed": len(failures),
        },
    }


def load_release_artifact_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase9_release_artifacts.v1":
        raise ValueError("release artifact manifest schema_version must be phase9_release_artifacts.v1")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("release artifact manifest must contain a non-empty artifacts array")
    return payload


def release_artifact_from_mapping(item: dict[str, Any]) -> ReleaseArtifact:
    artifact_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    path = str(item.get("path") or "").strip()
    evidence_scope = str(item.get("evidence_scope") or "local_release").strip()
    if not artifact_id:
        raise ValueError("artifact id is required")
    if not title:
        raise ValueError(f"{artifact_id} title is required")
    if not path:
        raise ValueError(f"{artifact_id} path is required")
    if evidence_scope not in {"local_release", "production_stack"}:
        raise ValueError(f"{artifact_id} evidence_scope must be local_release or production_stack")
    return ReleaseArtifact(
        artifact_id=artifact_id,
        title=title,
        path=path,
        required=bool(item.get("required", True)),
        include_in_bundle=bool(item.get("include_in_bundle", True)),
        evidence_scope=evidence_scope,
    )


def release_artifacts(payload: dict[str, Any], *, include_production: bool = False) -> list[ReleaseArtifact]:
    artifacts = [release_artifact_from_mapping(item) for item in payload["artifacts"]]
    if include_production:
        return artifacts
    return [item for item in artifacts if item.evidence_scope == "local_release"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_release_artifact_report(
    artifact_payload: dict[str, Any],
    *,
    project_root: Path,
    include_production: bool = False,
) -> dict[str, Any]:
    selected = release_artifacts(artifact_payload, include_production=include_production)
    items: list[dict[str, Any]] = []
    for artifact in selected:
        path = Path(artifact.path)
        if not path.is_absolute():
            path = project_root / path
        exists = path.is_file()
        item = {
            "id": artifact.artifact_id,
            "title": artifact.title,
            "path": artifact.path,
            "required": artifact.required,
            "include_in_bundle": artifact.include_in_bundle,
            "evidence_scope": artifact.evidence_scope,
            "exists": exists,
            "status": "present" if exists else "missing",
        }
        if exists:
            item["size_bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
        items.append(item)
    missing_required = [item for item in items if item["required"] and item["status"] != "present"]
    return {
        "schema_version": "phase9_release_artifact_report.v1",
        "source_schema_version": artifact_payload["schema_version"],
        "include_production": include_production,
        "status": "complete" if not missing_required else "incomplete",
        "artifacts": items,
        "missing_required": missing_required,
        "summary": {
            "total": len(items),
            "present": sum(1 for item in items if item["status"] == "present"),
            "missing": sum(1 for item in items if item["status"] == "missing"),
            "required_missing": len(missing_required),
        },
    }


def load_readiness_requirements(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase8_deployment_readiness_evidence.v1":
        raise ValueError("readiness requirements schema_version must be phase8_deployment_readiness_evidence.v1")
    items = payload.get("requirements")
    if not isinstance(items, list) or not items:
        raise ValueError("readiness requirements must contain a non-empty requirements array")
    return payload


def evidence_requirement_from_mapping(item: dict[str, Any]) -> EvidenceRequirement:
    evidence_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    scope = str(item.get("scope") or "").strip()
    evidence_type = str(item.get("type") or "").strip()
    path = str(item.get("path") or "").strip()
    if not evidence_id:
        raise ValueError("evidence id is required")
    if not title:
        raise ValueError(f"{evidence_id} title is required")
    if scope not in {"local_release", "production_stack"}:
        raise ValueError(f"{evidence_id} scope must be local_release or production_stack")
    if evidence_type not in {"detached_log", "json_status", "load_report", "searchability_audit"}:
        raise ValueError(f"{evidence_id} has unsupported evidence type: {evidence_type}")
    if not path:
        raise ValueError(f"{evidence_id} path is required")
    return EvidenceRequirement(
        evidence_id=evidence_id,
        title=title,
        scope=scope,
        evidence_type=evidence_type,
        path=path,
        required=bool(item.get("required", True)),
        blocks_deployment=bool(item.get("blocks_deployment", True)),
    )


def readiness_requirements(payload: dict[str, Any], *, include_production: bool = False) -> list[EvidenceRequirement]:
    requirements = [evidence_requirement_from_mapping(item) for item in payload["requirements"]]
    if include_production:
        return requirements
    return [item for item in requirements if item.scope == "local_release"]


def evaluate_evidence(requirement: EvidenceRequirement, project_root: Path) -> dict[str, Any]:
    evidence_path = Path(requirement.path)
    if not evidence_path.is_absolute():
        evidence_path = project_root / evidence_path
    base = {
        "id": requirement.evidence_id,
        "title": requirement.title,
        "scope": requirement.scope,
        "type": requirement.evidence_type,
        "path": requirement.path,
        "required": requirement.required,
        "blocks_deployment": requirement.blocks_deployment,
        "exists": evidence_path.is_file(),
    }
    if not evidence_path.is_file():
        return {**base, "status": "missing", "summary": "evidence file is not present"}
    if requirement.evidence_type == "detached_log":
        text = evidence_path.read_text(encoding="utf-8", errors="replace")
        passed = "exit_status=0" in text
        return {
            **base,
            "status": "passed" if passed else "failed",
            "summary": "detached run exited 0" if passed else "detached run did not exit 0",
        }
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    status_value = str(payload.get("status") or "").lower()
    if requirement.evidence_type == "load_report":
        passed = status_value == "pass"
        return {
            **base,
            "status": "passed" if passed else "failed",
            "summary": f"load report status={payload.get('status')}",
        }
    if requirement.evidence_type == "searchability_audit":
        incomplete = int(payload.get("incomplete_documents") or payload.get("incomplete_document_count") or 0)
        passed = incomplete == 0 if "status" not in payload else status_value in {"passed", "pass"}
        return {
            **base,
            "status": "passed" if passed else "failed",
            "summary": f"incomplete_documents={incomplete}",
        }
    passed = status_value in {"passed", "pass"}
    return {
        **base,
        "status": "passed" if passed else "failed",
        "summary": f"json status={payload.get('status')}",
    }


def build_readiness_pack(
    requirements_payload: dict[str, Any],
    *,
    project_root: Path,
    include_production: bool = False,
) -> dict[str, Any]:
    selected = readiness_requirements(requirements_payload, include_production=include_production)
    evidence = [evaluate_evidence(requirement, project_root) for requirement in selected]
    blockers = [
        item
        for item in evidence
        if item["blocks_deployment"] and item["required"] and item["status"] != "passed"
    ]
    missing_production = [
        item
        for item in evidence
        if item["scope"] == "production_stack" and item["status"] == "missing"
    ]
    if blockers:
        decision = "blocked"
    elif missing_production:
        decision = "needs_production_evidence"
    else:
        decision = "ready"
    return {
        "schema_version": "phase8_readiness_pack.v1",
        "source_schema_version": requirements_payload["schema_version"],
        "include_production": include_production,
        "decision": decision,
        "evidence": evidence,
        "blockers": blockers,
        "missing_production_evidence": missing_production,
        "summary": {
            "total": len(evidence),
            "passed": sum(1 for item in evidence if item["status"] == "passed"),
            "failed": sum(1 for item in evidence if item["status"] == "failed"),
            "missing": sum(1 for item in evidence if item["status"] == "missing"),
        },
    }


def load_ui_deployment_readiness_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase30_ui_deployment_readiness.v1":
        raise ValueError("UI deployment readiness manifest schema_version must be phase30_ui_deployment_readiness.v1")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("UI deployment readiness manifest must contain a non-empty evidence array")
    required_env = payload.get("required_environment")
    if not isinstance(required_env, list) or not required_env:
        raise ValueError("UI deployment readiness manifest must contain required_environment")
    return payload


def evaluate_ui_deployment_evidence(item: dict[str, Any], project_root: Path) -> dict[str, Any]:
    evidence_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    evidence_type = str(item.get("type") or "").strip()
    path_value = str(item.get("path") or "").strip()
    required = bool(item.get("required", True))
    if not evidence_id:
        raise ValueError("UI deployment evidence id is required")
    if not title:
        raise ValueError(f"{evidence_id} title is required")
    if evidence_type not in {"detached_log", "document", "package_script", "detached_mode", "file"}:
        raise ValueError(f"{evidence_id} has unsupported UI deployment evidence type: {evidence_type}")
    if not path_value:
        raise ValueError(f"{evidence_id} path is required")
    evidence_path = Path(path_value)
    if not evidence_path.is_absolute():
        evidence_path = project_root / evidence_path
    base = {
        "id": evidence_id,
        "title": title,
        "type": evidence_type,
        "path": path_value,
        "required": required,
        "exists": evidence_path.is_file(),
    }
    if not evidence_path.is_file():
        return {**base, "status": "missing", "summary": "evidence file is not present"}
    if evidence_type == "detached_log":
        text = evidence_path.read_text(encoding="utf-8", errors="replace")
        passed = "exit_status=0" in text
        return {
            **base,
            "status": "verified" if passed else "failed",
            "summary": "detached run exited 0" if passed else "detached run did not exit 0",
        }
    if evidence_type == "package_script":
        script_name = str(item.get("script_name") or "").strip()
        expected_contains = str(item.get("expected_contains") or "").strip()
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        command = str((payload.get("scripts") or {}).get(script_name) or "")
        verified = bool(script_name and command and (not expected_contains or expected_contains in command))
        return {
            **base,
            "script_name": script_name,
            "status": "verified" if verified else "failed",
            "summary": f"script {script_name} {'contains expected command' if verified else 'is missing or unexpected'}",
        }
    text = evidence_path.read_text(encoding="utf-8", errors="replace")
    if evidence_type == "detached_mode":
        mode_name = str(item.get("mode_name") or "").strip()
        expected_contains = str(item.get("expected_contains") or "").strip()
        verified = bool(mode_name and mode_name in text and (not expected_contains or expected_contains in text))
        return {
            **base,
            "mode_name": mode_name,
            "status": "verified" if verified else "failed",
            "summary": f"detached mode {mode_name} {'is present' if verified else 'is missing or unexpected'}",
        }
    return {
        **base,
        "status": "verified" if text.strip() else "failed",
        "summary": "file is present" if text.strip() else "file is empty",
    }


def evaluate_ui_deployment_environment(
    payload: dict[str, Any],
    *,
    environment: dict[str, str],
    include_environment: bool,
    deployment_environment: str,
) -> dict[str, Any]:
    required = payload.get("required_environment") or []
    dev_only = [str(item).strip() for item in payload.get("dev_only_environment") or [] if str(item).strip()]
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    if not include_environment:
        for item in required:
            name = str(item.get("name") or "").strip()
            checks.append(
                {
                    "name": name,
                    "category": str(item.get("category") or ""),
                    "required": bool(item.get("required", True)),
                    "secret": bool(item.get("secret", False)),
                    "status": "not_evaluated",
                    "summary": "hosted environment values were not inspected",
                }
            )
        return {
            "deployment_environment": deployment_environment,
            "included": False,
            "checks": checks,
            "dev_only_environment": [{"name": name, "status": "not_evaluated"} for name in dev_only],
            "blockers": [],
            "summary": "Hosted environment values require deployment-console review before cutover.",
        }
    for item in required:
        name = str(item.get("name") or "").strip()
        min_length = int(item.get("min_length") or 1)
        value = environment.get(name, "")
        required_flag = bool(item.get("required", True))
        secret = bool(item.get("secret", False))
        url_required = bool(item.get("url", False))
        present = bool(value)
        length_ok = len(value) >= min_length if present else False
        url_ok = value.startswith(("https://", "http://")) if url_required and present else not url_required
        status = "verified" if (not required_flag or (present and length_ok and url_ok)) else "missing"
        check = {
            "name": name,
            "category": str(item.get("category") or ""),
            "required": required_flag,
            "secret": secret,
            "status": status,
            "present": present,
            "meets_min_length": length_ok if secret else None,
            "url_scheme_ok": url_ok if url_required else None,
            "summary": "environment value is present and valid" if status == "verified" else "environment value is missing or invalid",
        }
        checks.append(check)
        if status != "verified" and required_flag:
            blockers.append({"id": f"env:{name}", "status": status, "summary": check["summary"]})
    dev_only_checks = []
    for name in dev_only:
        present = bool(environment.get(name))
        status = "failed" if deployment_environment in {"staging", "production"} and present else "verified"
        dev_check = {
            "name": name,
            "status": status,
            "present": present,
            "summary": "dev-only environment variable is absent" if status == "verified" else "dev-only environment variable must not be set",
        }
        dev_only_checks.append(dev_check)
        if status == "failed":
            blockers.append({"id": f"dev_env:{name}", "status": status, "summary": dev_check["summary"]})
    return {
        "deployment_environment": deployment_environment,
        "included": True,
        "checks": checks,
        "dev_only_environment": dev_only_checks,
        "blockers": blockers,
        "summary": "Hosted environment values were evaluated without exposing secret contents.",
    }


def build_ui_deployment_readiness_report(
    readiness_payload: dict[str, Any],
    *,
    project_root: Path,
    environment: dict[str, str] | None = None,
    include_environment: bool = False,
    deployment_environment: str = "staging",
) -> dict[str, Any]:
    evidence = [
        evaluate_ui_deployment_evidence(item, project_root)
        for item in readiness_payload["evidence"]
    ]
    env_report = evaluate_ui_deployment_environment(
        readiness_payload,
        environment=environment or {},
        include_environment=include_environment,
        deployment_environment=deployment_environment,
    )
    evidence_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in evidence
        if item["required"] and item["status"] != "verified"
    ]
    blockers = [*evidence_blockers, *env_report["blockers"]]
    if blockers:
        status = "blocked"
    elif include_environment:
        status = "ready_for_deployment_review"
    else:
        status = "ready_for_hosted_env_review"
    return {
        "schema_version": "phase30_ui_deployment_readiness_report.v1",
        "source_schema_version": readiness_payload["schema_version"],
        "target_release_tag": readiness_payload.get("target_release_tag"),
        "status": status,
        "deployment_environment": deployment_environment,
        "environment_included": include_environment,
        "evidence": evidence,
        "environment": env_report,
        "blockers": blockers,
        "summary": {
            "total_evidence": len(evidence),
            "verified_evidence": sum(1 for item in evidence if item["status"] == "verified"),
            "failed_evidence": sum(1 for item in evidence if item["status"] == "failed"),
            "missing_evidence": sum(1 for item in evidence if item["status"] == "missing"),
            "environment_checks": len(env_report["checks"]),
            "blockers": len(blockers),
        },
    }


def load_staging_cutover_dry_run_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase31_staging_cutover_dry_run.v1":
        raise ValueError("staging cutover manifest schema_version must be phase31_staging_cutover_dry_run.v1")
    required_reports = payload.get("required_reports")
    if not isinstance(required_reports, list) or not required_reports:
        raise ValueError("staging cutover manifest must contain a non-empty required_reports array")
    smoke_tests = payload.get("smoke_tests")
    if not isinstance(smoke_tests, list) or not smoke_tests:
        raise ValueError("staging cutover manifest must contain a non-empty smoke_tests array")
    rollback_steps = payload.get("rollback_steps")
    if not isinstance(rollback_steps, list) or not rollback_steps:
        raise ValueError("staging cutover manifest must contain rollback_steps")
    return payload


def evaluate_staging_cutover_report(item: dict[str, Any], project_root: Path) -> dict[str, Any]:
    report_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    report_type = str(item.get("type") or "").strip()
    path_value = str(item.get("path") or "").strip()
    required = bool(item.get("required", True))
    if not report_id:
        raise ValueError("staging cutover report id is required")
    if not title:
        raise ValueError(f"{report_id} title is required")
    if report_type not in {"json_status", "document", "file"}:
        raise ValueError(f"{report_id} has unsupported staging cutover report type: {report_type}")
    if not path_value:
        raise ValueError(f"{report_id} path is required")
    path = Path(path_value)
    if not path.is_absolute():
        path = project_root / path
    base = {
        "id": report_id,
        "title": title,
        "type": report_type,
        "path": path_value,
        "required": required,
        "exists": path.is_file(),
    }
    if not path.is_file():
        return {**base, "status": "missing", "summary": "required cutover evidence is not present"}
    result = {
        **base,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if report_type in {"document", "file"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            **result,
            "status": "verified" if text.strip() else "failed",
            "summary": "evidence file is present" if text.strip() else "evidence file is empty",
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_status = str(payload.get("status") or payload.get("decision") or "").strip()
    accepted_statuses = [
        str(status).strip()
        for status in item.get("accepted_statuses", [])
        if str(status).strip()
    ]
    verified = actual_status in accepted_statuses if accepted_statuses else bool(actual_status)
    return {
        **result,
        "status": "verified" if verified else "failed",
        "actual_status": actual_status,
        "accepted_statuses": accepted_statuses,
        "summary": f"json status={actual_status}",
    }


def staging_cutover_smoke_test_from_mapping(item: dict[str, Any]) -> dict[str, Any]:
    smoke_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    command = item.get("command")
    if not smoke_id:
        raise ValueError("staging cutover smoke test id is required")
    if not title:
        raise ValueError(f"{smoke_id} title is required")
    if not isinstance(command, list) or not command or not all(str(part).strip() for part in command):
        raise ValueError(f"{smoke_id} command must be a non-empty string array")
    requires_hosted = bool(item.get("requires_hosted_environment", False))
    required_before_cutover = bool(item.get("required_before_cutover", True))
    return {
        "id": smoke_id,
        "title": title,
        "command": [str(part) for part in command],
        "command_line": " ".join(shlex.quote(str(part)) for part in command),
        "requires_hosted_environment": requires_hosted,
        "required_before_cutover": required_before_cutover,
        "expected_evidence": str(item.get("expected_evidence") or "").strip(),
        "status": "requires_hosted_environment" if requires_hosted else "ready_to_run",
    }


def build_staging_cutover_dry_run(
    cutover_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(cutover_payload.get("target_release_tag") or "").strip()
    repo = str(cutover_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    reports = [
        evaluate_staging_cutover_report(item, project_root)
        for item in cutover_payload["required_reports"]
    ]
    smoke_tests = [staging_cutover_smoke_test_from_mapping(item) for item in cutover_payload["smoke_tests"]]
    rollback_steps = [
        {
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "action": str(item.get("action") or "").strip(),
            "owner": str(item.get("owner") or "operator").strip(),
        }
        for item in cutover_payload.get("rollback_steps", [])
    ]
    approvals = [
        {
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "required": bool(item.get("required", True)),
        }
        for item in cutover_payload.get("manual_approvals", [])
    ]
    blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in reports
        if item["required"] and item["status"] != "verified"
    ]
    for item in rollback_steps:
        if not item["id"] or not item["title"] or not item["action"]:
            blockers.append({"id": "rollback_step", "status": "failed", "summary": "rollback step is incomplete"})
    for item in approvals:
        if item["required"] and (not item["id"] or not item["title"]):
            blockers.append({"id": "manual_approval", "status": "failed", "summary": "manual approval is incomplete"})
    phase30_status = ""
    for item in reports:
        if item["id"] == "phase30_readiness_report":
            phase30_status = str(item.get("actual_status") or "")
    if blockers:
        status = "blocked"
    elif phase30_status == "ready_for_deployment_review":
        status = "ready_for_staging_cutover"
    else:
        status = "ready_for_hosted_env_setup"
    return {
        "schema_version": "phase31_staging_cutover_dry_run.v1",
        "source_schema_version": cutover_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "cutover_environment": str(cutover_payload.get("cutover_environment") or "staging"),
        "required_reports": reports,
        "smoke_tests": smoke_tests,
        "manual_approvals": approvals,
        "rollback_steps": rollback_steps,
        "blockers": blockers,
        "summary": {
            "total_reports": len(reports),
            "verified_reports": sum(1 for item in reports if item["status"] == "verified"),
            "failed_reports": sum(1 for item in reports if item["status"] == "failed"),
            "missing_reports": sum(1 for item in reports if item["status"] == "missing"),
            "smoke_tests": len(smoke_tests),
            "hosted_smoke_tests": sum(1 for item in smoke_tests if item["requires_hosted_environment"]),
            "rollback_steps": len(rollback_steps),
            "manual_approvals": len(approvals),
            "blockers": len(blockers),
        },
    }


def load_hosted_staging_execution_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase32_hosted_staging_execution.v1":
        raise ValueError("hosted staging execution manifest schema_version must be phase32_hosted_staging_execution.v1")
    required_reports = payload.get("required_reports")
    if not isinstance(required_reports, list) or not required_reports:
        raise ValueError("hosted staging execution manifest must contain a non-empty required_reports array")
    execution_steps = payload.get("execution_steps")
    if not isinstance(execution_steps, list) or not execution_steps:
        raise ValueError("hosted staging execution manifest must contain a non-empty execution_steps array")
    rollback_steps = payload.get("rollback_steps")
    if not isinstance(rollback_steps, list) or not rollback_steps:
        raise ValueError("hosted staging execution manifest must contain rollback_steps")
    return payload


def hosted_execution_step_from_mapping(item: dict[str, Any]) -> dict[str, Any]:
    step_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    command = item.get("command")
    if not step_id:
        raise ValueError("hosted staging execution step id is required")
    if not title:
        raise ValueError(f"{step_id} title is required")
    if command is not None and (
        not isinstance(command, list) or not command or not all(str(part).strip() for part in command)
    ):
        raise ValueError(f"{step_id} command must be a non-empty string array when provided")
    requires_hosted = bool(item.get("requires_hosted_environment", False))
    requires_manual = bool(item.get("requires_manual_action", False))
    required_before_exposure = bool(item.get("required_before_exposure", True))
    return {
        "id": step_id,
        "title": title,
        "description": str(item.get("description") or "").strip(),
        "command": [str(part) for part in command] if isinstance(command, list) else [],
        "command_line": " ".join(shlex.quote(str(part)) for part in command) if isinstance(command, list) else "",
        "expected_evidence": str(item.get("expected_evidence") or "").strip(),
        "requires_hosted_environment": requires_hosted,
        "requires_manual_action": requires_manual,
        "required_before_exposure": required_before_exposure,
        "status": "requires_hosted_environment" if requires_hosted else "ready_to_run",
    }


def build_hosted_staging_execution_pack(
    execution_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(execution_payload.get("target_release_tag") or "").strip()
    repo = str(execution_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    reports = [
        evaluate_staging_cutover_report(item, project_root)
        for item in execution_payload["required_reports"]
    ]
    execution_steps = [hosted_execution_step_from_mapping(item) for item in execution_payload["execution_steps"]]
    rollback_steps = [
        {
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "action": str(item.get("action") or "").strip(),
            "owner": str(item.get("owner") or "operator").strip(),
        }
        for item in execution_payload.get("rollback_steps", [])
    ]
    approvals = [
        {
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "required": bool(item.get("required", True)),
        }
        for item in execution_payload.get("manual_approvals", [])
    ]
    blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in reports
        if item["required"] and item["status"] != "verified"
    ]
    for item in execution_steps:
        if item["required_before_exposure"] and not item["description"] and not item["command"]:
            blockers.append({"id": item["id"], "status": "failed", "summary": "execution step lacks description or command"})
    for item in rollback_steps:
        if not item["id"] or not item["title"] or not item["action"]:
            blockers.append({"id": "rollback_step", "status": "failed", "summary": "rollback step is incomplete"})
    for item in approvals:
        if item["required"] and (not item["id"] or not item["title"]):
            blockers.append({"id": "manual_approval", "status": "failed", "summary": "manual approval is incomplete"})
    phase31_status = ""
    for item in reports:
        if item["id"] == "phase31_cutover_dry_run":
            phase31_status = str(item.get("actual_status") or "")
    if blockers:
        status = "blocked"
    elif phase31_status == "ready_for_staging_cutover":
        status = "ready_for_hosted_staging_execution"
    else:
        status = "ready_for_hosted_configuration"
    return {
        "schema_version": "phase32_hosted_staging_execution.v1",
        "source_schema_version": execution_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(execution_payload.get("execution_environment") or "staging"),
        "required_reports": reports,
        "execution_steps": execution_steps,
        "manual_approvals": approvals,
        "rollback_steps": rollback_steps,
        "blockers": blockers,
        "summary": {
            "total_reports": len(reports),
            "verified_reports": sum(1 for item in reports if item["status"] == "verified"),
            "failed_reports": sum(1 for item in reports if item["status"] == "failed"),
            "missing_reports": sum(1 for item in reports if item["status"] == "missing"),
            "execution_steps": len(execution_steps),
            "hosted_execution_steps": sum(1 for item in execution_steps if item["requires_hosted_environment"]),
            "manual_execution_steps": sum(1 for item in execution_steps if item["requires_manual_action"]),
            "rollback_steps": len(rollback_steps),
            "manual_approvals": len(approvals),
            "blockers": len(blockers),
        },
    }


def load_hosted_staging_validation_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase33_hosted_staging_validation.v1":
        raise ValueError("hosted staging validation manifest schema_version must be phase33_hosted_staging_validation.v1")
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted staging validation manifest must contain a non-empty prerequisites array")
    hosted_evidence = payload.get("hosted_evidence")
    if not isinstance(hosted_evidence, list) or not hosted_evidence:
        raise ValueError("hosted staging validation manifest must contain a non-empty hosted_evidence array")
    return payload


def _json_field_matches(payload: dict[str, Any], field_path: str, expected: Any) -> tuple[bool, Any]:
    current: Any = payload
    for part in field_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return current == expected, current


def evaluate_hosted_staging_validation_item(
    item: dict[str, Any],
    project_root: Path,
    *,
    missing_status: str,
) -> dict[str, Any]:
    evidence_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    evidence_type = str(item.get("type") or "").strip()
    path_value = str(item.get("path") or "").strip()
    required = bool(item.get("required", True))
    if not evidence_id:
        raise ValueError("hosted staging validation evidence id is required")
    if not title:
        raise ValueError(f"{evidence_id} title is required")
    if evidence_type not in {"json_status", "detached_log", "document", "file"}:
        raise ValueError(f"{evidence_id} has unsupported hosted staging validation type: {evidence_type}")
    if not path_value:
        raise ValueError(f"{evidence_id} path is required")
    path = Path(path_value)
    if not path.is_absolute():
        path = project_root / path
    base = {
        "id": evidence_id,
        "title": title,
        "type": evidence_type,
        "path": path_value,
        "required": required,
        "exists": path.is_file(),
    }
    if not path.is_file():
        return {**base, "status": missing_status, "summary": "evidence is not present"}
    result = {
        **base,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }
    if evidence_type == "detached_log":
        text = path.read_text(encoding="utf-8", errors="replace")
        verified = "exit_status=0" in text
        return {
            **result,
            "status": "verified" if verified else "failed",
            "summary": "detached run exited 0" if verified else "detached run did not exit 0",
        }
    if evidence_type in {"document", "file"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            **result,
            "status": "verified" if text.strip() else "failed",
            "summary": "evidence file is present" if text.strip() else "evidence file is empty",
        }
    required_fields = item.get("required_fields") or {}
    if not isinstance(required_fields, dict):
        raise ValueError(f"{evidence_id} required_fields must be an object when provided")
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual_status = str(payload.get("status") or payload.get("decision") or "").strip()
    accepted_statuses = [
        str(status).strip()
        for status in item.get("accepted_statuses", [])
        if str(status).strip()
    ]
    pending_statuses = [
        str(status).strip()
        for status in item.get("pending_statuses", [])
        if str(status).strip()
    ]
    if accepted_statuses and actual_status in accepted_statuses:
        status = "verified"
    elif pending_statuses and actual_status in pending_statuses:
        status = "pending"
    elif not accepted_statuses and actual_status:
        status = "verified"
    else:
        status = "failed"
    field_mismatches = []
    for field_path, expected in required_fields.items():
        matches, actual = _json_field_matches(payload, str(field_path), expected)
        if not matches:
            field_mismatches.append(
                {
                    "field": str(field_path),
                    "expected": expected,
                    "actual": actual,
                }
            )
    if status == "verified" and field_mismatches:
        status = "failed"
    summary = f"json status={actual_status}"
    if field_mismatches:
        summary = f"{summary}; required field mismatch"
    return {
        **result,
        "status": status,
        "actual_status": actual_status,
        "accepted_statuses": accepted_statuses,
        "pending_statuses": pending_statuses,
        "required_fields": required_fields,
        "field_mismatches": field_mismatches,
        "summary": summary,
    }


def build_hosted_staging_validation_report(
    validation_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(validation_payload.get("target_release_tag") or "").strip()
    repo = str(validation_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in validation_payload["prerequisites"]
    ]
    hosted_evidence = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
        for item in validation_payload["hosted_evidence"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    hosted_failures = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in hosted_evidence
        if item["required"] and item["status"] == "failed"
    ]
    pending_hosted = [
        item for item in hosted_evidence if item["required"] and item["status"] == "pending"
    ]
    blockers = [*prerequisite_blockers, *hosted_failures]
    if blockers:
        status = "blocked"
    elif pending_hosted:
        status = "awaiting_hosted_execution"
    else:
        status = "hosted_staging_validated"
    return {
        "schema_version": "phase33_hosted_staging_validation.v1",
        "source_schema_version": validation_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(validation_payload.get("execution_environment") or "staging"),
        "prerequisites": prerequisites,
        "hosted_evidence": hosted_evidence,
        "pending_hosted_evidence": pending_hosted,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_hosted_evidence": len(hosted_evidence),
            "verified_hosted_evidence": sum(1 for item in hosted_evidence if item["status"] == "verified"),
            "pending_hosted_evidence": len(pending_hosted),
            "failed_hosted_evidence": sum(1 for item in hosted_evidence if item["status"] == "failed"),
            "blockers": len(blockers),
        },
    }


def load_backend_db_staging_validation_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase34_backend_db_staging_validation.v1":
        raise ValueError("backend DB staging validation manifest schema_version must be phase34_backend_db_staging_validation.v1")
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("backend DB staging validation manifest must contain a non-empty prerequisites array")
    staging_evidence = payload.get("staging_evidence")
    if not isinstance(staging_evidence, list) or not staging_evidence:
        raise ValueError("backend DB staging validation manifest must contain a non-empty staging_evidence array")
    return payload


def build_backend_db_staging_validation_report(
    validation_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(validation_payload.get("target_release_tag") or "").strip()
    repo = str(validation_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in validation_payload["prerequisites"]
    ]
    staging_evidence = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
        for item in validation_payload["staging_evidence"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    staging_failures = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in staging_evidence
        if item["required"] and item["status"] == "failed"
    ]
    pending_staging = [
        item for item in staging_evidence if item["required"] and item["status"] == "pending"
    ]
    blockers = [*prerequisite_blockers, *staging_failures]
    if blockers:
        status = "blocked"
    elif pending_staging:
        status = "awaiting_backend_db_staging_evidence"
    else:
        status = "backend_db_staging_validated"
    return {
        "schema_version": "phase34_backend_db_staging_validation.v1",
        "source_schema_version": validation_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(validation_payload.get("execution_environment") or "staging"),
        "database_mode": str(validation_payload.get("database_mode") or "read_only_validation"),
        "prerequisites": prerequisites,
        "staging_evidence": staging_evidence,
        "pending_staging_evidence": pending_staging,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_staging_evidence": len(staging_evidence),
            "verified_staging_evidence": sum(1 for item in staging_evidence if item["status"] == "verified"),
            "pending_staging_evidence": len(pending_staging),
            "failed_staging_evidence": sum(1 for item in staging_evidence if item["status"] == "failed"),
            "blockers": len(blockers),
        },
    }


def load_hosted_evidence_capture_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase35_hosted_evidence_capture.v1":
        raise ValueError("hosted evidence capture manifest schema_version must be phase35_hosted_evidence_capture.v1")
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted evidence capture manifest must contain a non-empty prerequisites array")
    required_environment = payload.get("required_environment")
    if not isinstance(required_environment, list) or not required_environment:
        raise ValueError("hosted evidence capture manifest must contain a non-empty required_environment array")
    capture_tasks = payload.get("capture_tasks")
    if not isinstance(capture_tasks, list) or not capture_tasks:
        raise ValueError("hosted evidence capture manifest must contain a non-empty capture_tasks array")
    return payload


def load_hosted_evidence_capture_runner_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase36_hosted_evidence_capture_runner.v1":
        raise ValueError(
            "hosted evidence capture runner manifest schema_version must be "
            "phase36_hosted_evidence_capture_runner.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted evidence capture runner manifest must contain a non-empty prerequisites array")
    capture_manifest_path = str(payload.get("capture_manifest_path") or "").strip()
    if not capture_manifest_path:
        raise ValueError("hosted evidence capture runner manifest must define capture_manifest_path")
    response_expectations = payload.get("response_expectations", [])
    if not isinstance(response_expectations, list):
        raise ValueError("hosted evidence capture runner response_expectations must be an array")
    return payload


def load_hosted_capture_acceptance_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase37_hosted_capture_acceptance.v1":
        raise ValueError(
            "hosted capture acceptance manifest schema_version must be phase37_hosted_capture_acceptance.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted capture acceptance manifest must contain a non-empty prerequisites array")
    captured_evidence = payload.get("captured_evidence")
    if not isinstance(captured_evidence, list) or not captured_evidence:
        raise ValueError("hosted capture acceptance manifest must contain a non-empty captured_evidence array")
    forbidden_terms = payload.get("forbidden_terms", [])
    if not isinstance(forbidden_terms, list):
        raise ValueError("hosted capture acceptance manifest forbidden_terms must be an array")
    return payload


def load_hosted_capture_execution_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase38_hosted_capture_execution.v1":
        raise ValueError(
            "hosted capture execution manifest schema_version must be phase38_hosted_capture_execution.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted capture execution manifest must contain a non-empty prerequisites array")
    execution_chain = payload.get("execution_chain")
    if not isinstance(execution_chain, list) or not execution_chain:
        raise ValueError("hosted capture execution manifest must contain a non-empty execution_chain array")
    report_outputs = payload.get("report_outputs")
    if not isinstance(report_outputs, dict) or not report_outputs:
        raise ValueError("hosted capture execution manifest must contain report_outputs")
    return payload


def load_hosted_environment_config_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase39_hosted_environment_config.v1":
        raise ValueError(
            "hosted environment config manifest schema_version must be phase39_hosted_environment_config.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted environment config manifest must contain a non-empty prerequisites array")
    required_environment = payload.get("required_environment")
    if not isinstance(required_environment, list) or not required_environment:
        raise ValueError("hosted environment config manifest must contain a non-empty required_environment array")
    command_recipes = payload.get("command_recipes")
    if not isinstance(command_recipes, list) or not command_recipes:
        raise ValueError("hosted environment config manifest must contain a non-empty command_recipes array")
    evidence_outputs = payload.get("evidence_outputs")
    if not isinstance(evidence_outputs, list) or not evidence_outputs:
        raise ValueError("hosted environment config manifest must contain a non-empty evidence_outputs array")
    return payload


def load_hosted_dry_run_evidence_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase40_hosted_dry_run_evidence.v1":
        raise ValueError(
            "hosted dry-run evidence manifest schema_version must be phase40_hosted_dry_run_evidence.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted dry-run evidence manifest must contain a non-empty prerequisites array")
    dry_run_evidence = payload.get("dry_run_evidence")
    if not isinstance(dry_run_evidence, list) or not dry_run_evidence:
        raise ValueError("hosted dry-run evidence manifest must contain a non-empty dry_run_evidence array")
    forbidden_terms = payload.get("forbidden_terms", [])
    if not isinstance(forbidden_terms, list):
        raise ValueError("hosted dry-run evidence manifest forbidden_terms must be an array")
    return payload


def load_hosted_capture_execution_evidence_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase41_hosted_capture_execution_evidence.v1":
        raise ValueError(
            "hosted capture execution evidence manifest schema_version must be "
            "phase41_hosted_capture_execution_evidence.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("hosted capture execution evidence manifest must contain a non-empty prerequisites array")
    execution_evidence = payload.get("execution_evidence")
    if not isinstance(execution_evidence, list) or not execution_evidence:
        raise ValueError("hosted capture execution evidence manifest must contain a non-empty execution_evidence array")
    forbidden_terms = payload.get("forbidden_terms", [])
    if not isinstance(forbidden_terms, list):
        raise ValueError("hosted capture execution evidence manifest forbidden_terms must be an array")
    return payload


def load_staging_acceptance_decision_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase42_staging_acceptance_decision.v1":
        raise ValueError(
            "staging acceptance decision manifest schema_version must be "
            "phase42_staging_acceptance_decision.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("staging acceptance decision manifest must contain a non-empty prerequisites array")
    decision_evidence = payload.get("decision_evidence")
    if not isinstance(decision_evidence, list) or not decision_evidence:
        raise ValueError("staging acceptance decision manifest must contain a non-empty decision_evidence array")
    required_acceptance = payload.get("required_acceptance")
    if not isinstance(required_acceptance, list) or not required_acceptance:
        raise ValueError("staging acceptance decision manifest must contain a non-empty required_acceptance array")
    residual_risks = payload.get("residual_risks")
    if not isinstance(residual_risks, list) or not residual_risks:
        raise ValueError("staging acceptance decision manifest must contain a non-empty residual_risks array")
    forbidden_terms = payload.get("forbidden_terms", [])
    if not isinstance(forbidden_terms, list):
        raise ValueError("staging acceptance decision manifest forbidden_terms must be an array")
    return payload


def load_production_cutover_readiness_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase43_production_cutover_readiness.v1":
        raise ValueError(
            "production cutover readiness manifest schema_version must be "
            "phase43_production_cutover_readiness.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("production cutover readiness manifest must contain a non-empty prerequisites array")
    readiness_evidence = payload.get("readiness_evidence")
    if not isinstance(readiness_evidence, list) or not readiness_evidence:
        raise ValueError("production cutover readiness manifest must contain a non-empty readiness_evidence array")
    rollback_evidence = payload.get("rollback_evidence")
    if not isinstance(rollback_evidence, list) or not rollback_evidence:
        raise ValueError("production cutover readiness manifest must contain a non-empty rollback_evidence array")
    required_environment = payload.get("required_environment")
    if not isinstance(required_environment, list) or not required_environment:
        raise ValueError("production cutover readiness manifest must contain a non-empty required_environment array")
    forbidden_terms = payload.get("forbidden_terms", [])
    if not isinstance(forbidden_terms, list):
        raise ValueError("production cutover readiness manifest forbidden_terms must be an array")
    return payload


def load_production_cutover_dry_run_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != "phase44_production_cutover_dry_run.v1":
        raise ValueError(
            "production cutover dry-run manifest schema_version must be "
            "phase44_production_cutover_dry_run.v1"
        )
    prerequisites = payload.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise ValueError("production cutover dry-run manifest must contain a non-empty prerequisites array")
    readiness_reports = payload.get("readiness_reports")
    if not isinstance(readiness_reports, list) or not readiness_reports:
        raise ValueError("production cutover dry-run manifest must contain a non-empty readiness_reports array")
    dry_run_steps = payload.get("dry_run_steps")
    if not isinstance(dry_run_steps, list) or not dry_run_steps:
        raise ValueError("production cutover dry-run manifest must contain a non-empty dry_run_steps array")
    rollback_steps = payload.get("rollback_steps")
    if not isinstance(rollback_steps, list) or not rollback_steps:
        raise ValueError("production cutover dry-run manifest must contain a non-empty rollback_steps array")
    owner_approvals = payload.get("owner_approvals")
    if not isinstance(owner_approvals, list) or not owner_approvals:
        raise ValueError("production cutover dry-run manifest must contain a non-empty owner_approvals array")
    forbidden_terms = payload.get("forbidden_terms", [])
    if not isinstance(forbidden_terms, list):
        raise ValueError("production cutover dry-run manifest forbidden_terms must be an array")
    return payload


def evaluate_hosted_capture_environment(
    payload: dict[str, Any],
    *,
    environment: dict[str, str],
    include_environment: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for item in payload.get("required_environment", []):
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("hosted evidence capture environment name is required")
        required = bool(item.get("required", True))
        secret = bool(item.get("secret", False))
        min_length = int(item.get("min_length") or 1)
        expected_value = item.get("expected_value")
        url_required = bool(item.get("url", False))
        if not include_environment:
            checks.append(
                {
                    "name": name,
                    "category": str(item.get("category") or ""),
                    "required": required,
                    "secret": secret,
                    "status": "not_evaluated",
                    "summary": "hosted capture environment was not inspected",
                }
            )
            continue
        value = environment.get(name, "")
        present = bool(value)
        length_ok = len(value) >= min_length if present else False
        url_ok = value.startswith(("https://", "http://")) if url_required and present else not url_required
        expected_ok = str(value).strip().lower() == str(expected_value).strip().lower() if expected_value is not None else True
        verified = (not required or present) and (not present or length_ok) and url_ok and expected_ok
        status = "verified" if verified else "missing"
        check = {
            "name": name,
            "category": str(item.get("category") or ""),
            "required": required,
            "secret": secret,
            "status": status,
            "present": present,
            "meets_min_length": length_ok if secret else None,
            "url_scheme_ok": url_ok if url_required else None,
            "expected_value_matched": expected_ok if expected_value is not None else None,
            "summary": "environment value is present and valid" if status == "verified" else "environment value is missing or invalid",
        }
        checks.append(check)
        if required and status != "verified":
            blockers.append({"id": f"env:{name}", "status": status, "summary": check["summary"]})
    return {
        "included": include_environment,
        "checks": checks,
        "blockers": blockers,
        "summary": "Hosted capture environment evaluated without exposing secret values."
        if include_environment
        else "Hosted capture environment values were not inspected.",
    }


def hosted_capture_task_from_mapping(item: dict[str, Any], *, environment_ready: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
    task_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    task_type = str(item.get("type") or "").strip()
    evidence_output = str(item.get("evidence_output") or "").strip()
    if not task_id:
        raise ValueError("hosted evidence capture task id is required")
    if not title:
        raise ValueError(f"{task_id} title is required")
    if task_type not in {"http_check", "signed_http_check", "operator_json"}:
        raise ValueError(f"{task_id} has unsupported hosted evidence capture task type: {task_type}")
    if not evidence_output:
        raise ValueError(f"{task_id} evidence_output is required")
    writes_database = bool(item.get("writes_database", False))
    write_classification = str(item.get("write_classification") or "").strip()
    blockers: list[dict[str, str]] = []
    if writes_database and write_classification not in {"audit_event_only"}:
        blockers.append(
            {
                "id": task_id,
                "status": "failed",
                "summary": "DB-writing capture tasks must declare an allowed write classification",
            }
        )
    method = str(item.get("method") or "").strip().upper()
    path_template = str(item.get("path_template") or "").strip()
    if task_type in {"http_check", "signed_http_check"} and (method not in {"GET", "POST"} or not path_template):
        blockers.append({"id": task_id, "status": "failed", "summary": "HTTP capture task is incomplete"})
    return {
        "id": task_id,
        "title": title,
        "type": task_type,
        "method": method,
        "path_template": path_template,
        "requires_signed_auth": task_type == "signed_http_check",
        "writes_database": writes_database,
        "write_classification": write_classification or None,
        "evidence_output": evidence_output,
        "phase34_evidence_id": str(item.get("phase34_evidence_id") or "").strip(),
        "instructions": str(item.get("instructions") or "").strip(),
        "status": "ready_for_hosted_execution" if environment_ready else "requires_hosted_environment",
    }, blockers


def build_hosted_evidence_capture_plan(
    capture_payload: dict[str, Any],
    *,
    project_root: Path,
    environment: dict[str, str] | None = None,
    include_environment: bool = False,
) -> dict[str, Any]:
    target_tag = str(capture_payload.get("target_release_tag") or "").strip()
    repo = str(capture_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in capture_payload["prerequisites"]
    ]
    env_report = evaluate_hosted_capture_environment(
        capture_payload,
        environment=environment or {},
        include_environment=include_environment,
    )
    environment_ready = include_environment and not env_report["blockers"]
    capture_tasks: list[dict[str, Any]] = []
    task_blockers: list[dict[str, str]] = []
    for item in capture_payload["capture_tasks"]:
        task, blockers = hosted_capture_task_from_mapping(item, environment_ready=environment_ready)
        capture_tasks.append(task)
        task_blockers.extend(blockers)
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    blockers = [*prerequisite_blockers, *env_report["blockers"], *task_blockers]
    if blockers:
        status = "blocked"
    elif environment_ready:
        status = "ready_for_capture_execution"
    else:
        status = "ready_for_hosted_capture_configuration"
    return {
        "schema_version": "phase35_hosted_evidence_capture.v1",
        "source_schema_version": capture_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(capture_payload.get("execution_environment") or "staging"),
        "prerequisites": prerequisites,
        "environment": env_report,
        "capture_tasks": capture_tasks,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "environment_checks": len(env_report["checks"]),
            "capture_tasks": len(capture_tasks),
            "signed_capture_tasks": sum(1 for item in capture_tasks if item["requires_signed_auth"]),
            "db_writing_capture_tasks": sum(1 for item in capture_tasks if item["writes_database"]),
            "blockers": len(blockers),
        },
    }


def hosted_config_command_from_mapping(item: dict[str, Any], *, environment_ready: bool) -> tuple[dict[str, Any], list[dict[str, str]]]:
    recipe_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    command = item.get("command")
    requires_environment = bool(item.get("requires_environment", False))
    executes_capture = bool(item.get("executes_capture", False))
    blockers: list[dict[str, str]] = []
    if not recipe_id:
        raise ValueError("hosted environment config command recipe id is required")
    if not title:
        raise ValueError(f"{recipe_id} title is required")
    if not isinstance(command, list) or not command or not all(str(part).strip() for part in command):
        raise ValueError(f"{recipe_id} command must be a non-empty string array")
    command_parts = [str(part) for part in command]
    if (requires_environment or executes_capture) and "scripts/run_phase38_hosted_capture_execution.py" not in command_parts:
        blockers.append(
            {
                "id": recipe_id,
                "status": "failed",
                "summary": "Phase 39 command recipes must call the Phase 38 orchestrator",
            }
        )
    has_include_environment = "--include-environment" in command_parts
    has_execute = "--execute" in command_parts
    if requires_environment and not has_include_environment:
        blockers.append(
            {
                "id": recipe_id,
                "status": "failed",
                "summary": "hosted command recipes that require environment must include --include-environment",
            }
        )
    if executes_capture and not (has_execute and has_include_environment):
        blockers.append(
            {
                "id": recipe_id,
                "status": "failed",
                "summary": "hosted execution recipes must include --execute and --include-environment",
            }
        )
    if not executes_capture and has_execute:
        blockers.append(
            {
                "id": recipe_id,
                "status": "failed",
                "summary": "dry-run command recipes must not include --execute",
            }
        )
    return {
        "id": recipe_id,
        "title": title,
        "command": command_parts,
        "command_line": " ".join(shlex.quote(part) for part in command_parts),
        "requires_environment": requires_environment,
        "executes_capture": executes_capture,
        "expected_status": str(item.get("expected_status") or "").strip(),
        "status": "ready" if not requires_environment or environment_ready else "requires_hosted_environment",
    }, blockers


def build_hosted_environment_config_pack(
    config_payload: dict[str, Any],
    *,
    project_root: Path,
    environment: dict[str, str] | None = None,
    include_environment: bool = False,
    phase35_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_tag = str(config_payload.get("target_release_tag") or "").strip()
    repo = str(config_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in config_payload["prerequisites"]
    ]
    env_report = evaluate_hosted_capture_environment(
        config_payload,
        environment=environment or {},
        include_environment=include_environment,
    )
    environment_ready = include_environment and not env_report["blockers"]
    commands: list[dict[str, Any]] = []
    command_blockers: list[dict[str, str]] = []
    for item in config_payload["command_recipes"]:
        command, blockers = hosted_config_command_from_mapping(item, environment_ready=environment_ready)
        commands.append(command)
        command_blockers.extend(blockers)
    evidence_outputs = [
        {
            "id": str(item.get("id") or "").strip(),
            "title": str(item.get("title") or "").strip(),
            "path": str(item.get("path") or "").strip(),
            "category": str(item.get("category") or "").strip(),
            "committable": bool(item.get("committable", False)),
        }
        for item in config_payload["evidence_outputs"]
    ]
    evidence_blockers = [
        {
            "id": item["id"] or "evidence_output",
            "status": "failed",
            "summary": "evidence outputs must have id, title, path, and remain non-committable",
        }
        for item in evidence_outputs
        if not item["id"] or not item["title"] or not item["path"] or item["committable"]
    ]
    environment_sync_blockers: list[dict[str, str]] = []
    if phase35_payload is not None:
        expected_names = {str(item.get("name") or "").strip() for item in phase35_payload.get("required_environment", [])}
        actual_names = {str(item.get("name") or "").strip() for item in config_payload.get("required_environment", [])}
        if expected_names != actual_names:
            environment_sync_blockers.append(
                {
                    "id": "phase35_environment_sync",
                    "status": "failed",
                    "summary": "Phase 39 environment requirements must match Phase 35",
                }
            )
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    blockers = [
        *prerequisite_blockers,
        *env_report["blockers"],
        *command_blockers,
        *evidence_blockers,
        *environment_sync_blockers,
    ]
    if blockers:
        status = "blocked"
    elif environment_ready:
        status = "ready_for_hosted_capture_dry_run"
    else:
        status = "awaiting_hosted_environment_configuration"
    return {
        "schema_version": "phase39_hosted_environment_config.v1",
        "source_schema_version": config_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(config_payload.get("execution_environment") or "staging"),
        "prerequisites": prerequisites,
        "environment": env_report,
        "command_recipes": commands,
        "evidence_outputs": evidence_outputs,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "environment_checks": len(env_report["checks"]),
            "command_recipes": len(commands),
            "execution_recipes": sum(1 for item in commands if item["executes_capture"]),
            "evidence_outputs": len(evidence_outputs),
            "blockers": len(blockers),
        },
    }


def evaluate_hosted_dry_run_evidence(
    item: dict[str, Any],
    project_root: Path,
    *,
    forbidden_terms: list[str],
) -> dict[str, Any]:
    result = evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
    if not result["exists"]:
        return result
    path = Path(str(result["path"]))
    if not path.is_absolute():
        path = project_root / path
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized_text = text.lower()
    matched_terms = [term for term in forbidden_terms if term and term.lower() in normalized_text]
    if not matched_terms:
        return {**result, "forbidden_content_matches": []}
    return {
        **result,
        "status": "failed",
        "forbidden_content_matches": matched_terms,
        "summary": "dry-run evidence contains forbidden hosted content",
    }


def build_hosted_dry_run_evidence_report(
    dry_run_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(dry_run_payload.get("target_release_tag") or "").strip()
    repo = str(dry_run_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    forbidden_terms = [str(term).strip() for term in dry_run_payload.get("forbidden_terms", []) if str(term).strip()]
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in dry_run_payload["prerequisites"]
    ]
    dry_run_evidence = [
        evaluate_hosted_dry_run_evidence(item, project_root, forbidden_terms=forbidden_terms)
        for item in dry_run_payload["dry_run_evidence"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    evidence_failures = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in dry_run_evidence
        if item["required"] and item["status"] == "failed"
    ]
    pending_evidence = [
        item for item in dry_run_evidence if item["required"] and item["status"] == "pending"
    ]
    statuses = {item["id"]: str(item.get("actual_status") or "") for item in dry_run_evidence}
    phase39_status = statuses.get("phase39_config_pack", "")
    phase38_status = statuses.get("phase38_hosted_dry_run", "")
    blockers = [*prerequisite_blockers, *evidence_failures]
    if blockers:
        status = "blocked"
    elif phase39_status != "ready_for_hosted_capture_dry_run":
        status = "awaiting_hosted_environment_configuration"
    elif phase38_status != "ready_for_hosted_capture_execution":
        status = "awaiting_hosted_dry_run_evidence"
    else:
        status = "hosted_dry_run_validated"
    return {
        "schema_version": "phase40_hosted_dry_run_evidence.v1",
        "source_schema_version": dry_run_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(dry_run_payload.get("execution_environment") or "staging"),
        "prerequisites": prerequisites,
        "dry_run_evidence": dry_run_evidence,
        "pending_dry_run_evidence": pending_evidence,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_dry_run_evidence": len(dry_run_evidence),
            "verified_dry_run_evidence": sum(1 for item in dry_run_evidence if item["status"] == "verified"),
            "pending_dry_run_evidence": len(pending_evidence),
            "failed_dry_run_evidence": sum(1 for item in dry_run_evidence if item["status"] == "failed"),
            "forbidden_terms": len(forbidden_terms),
            "blockers": len(blockers),
        },
    }


def evaluate_hosted_capture_execution_evidence(
    item: dict[str, Any],
    project_root: Path,
    *,
    forbidden_terms: list[str],
) -> dict[str, Any]:
    result = evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
    result = {**result, "group": str(item.get("group") or "").strip()}
    if not result["exists"]:
        return result
    path = Path(str(result["path"]))
    if not path.is_absolute():
        path = project_root / path
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized_text = text.lower()
    matched_terms = [term for term in forbidden_terms if term and term.lower() in normalized_text]
    if not matched_terms:
        return {**result, "forbidden_content_matches": []}
    return {
        **result,
        "status": "failed",
        "forbidden_content_matches": matched_terms,
        "summary": "execution evidence contains forbidden hosted content",
    }


def build_hosted_capture_execution_evidence_report(
    execution_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(execution_payload.get("target_release_tag") or "").strip()
    repo = str(execution_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    forbidden_terms = [str(term).strip() for term in execution_payload.get("forbidden_terms", []) if str(term).strip()]
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in execution_payload["prerequisites"]
    ]
    execution_evidence = [
        evaluate_hosted_capture_execution_evidence(item, project_root, forbidden_terms=forbidden_terms)
        for item in execution_payload["execution_evidence"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    evidence_failures = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in execution_evidence
        if item["required"] and item["status"] == "failed"
    ]
    pending_evidence = [
        item for item in execution_evidence if item["required"] and item["status"] == "pending"
    ]
    statuses = {item["id"]: str(item.get("actual_status") or "") for item in execution_evidence}
    phase40_status = statuses.get("phase40_dry_run_evidence", "")
    phase38_status = statuses.get("phase38_execution_report", "")
    phase36_status = statuses.get("phase36_capture_run", "")
    phase34_status = statuses.get("phase34_backend_db_validation", "")
    phase37_status = statuses.get("phase37_capture_acceptance", "")
    captured_pending = [
        item for item in pending_evidence if item.get("group") == "captured_evidence"
    ]
    blockers = [*prerequisite_blockers, *evidence_failures]
    if phase36_status == "hosted_evidence_captured" and captured_pending:
        blockers.extend(
            {
                "id": item["id"],
                "status": "pending",
                "summary": "captured execution evidence is missing after Phase 36 captured evidence",
            }
            for item in captured_pending
        )
    execution_statuses = {
        "hosted_capture_executed_pending_backend_db_validation",
        "hosted_capture_executed_pending_acceptance",
        "hosted_capture_execution_accepted",
    }
    if blockers:
        status = "blocked"
    elif phase40_status != "hosted_dry_run_validated":
        status = "awaiting_hosted_dry_run_validation"
    elif phase38_status not in execution_statuses or phase36_status != "hosted_evidence_captured":
        status = "awaiting_hosted_capture_execution"
    elif phase34_status != "backend_db_staging_validated":
        status = "hosted_capture_executed_pending_backend_db_validation"
    elif phase37_status != "hosted_capture_accepted":
        status = "hosted_capture_executed_pending_acceptance"
    else:
        status = "hosted_capture_execution_evidence_validated"
    return {
        "schema_version": "phase41_hosted_capture_execution_evidence.v1",
        "source_schema_version": execution_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(execution_payload.get("execution_environment") or "staging"),
        "execution_evidence": execution_evidence,
        "pending_execution_evidence": pending_evidence,
        "prerequisites": prerequisites,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_execution_evidence": len(execution_evidence),
            "verified_execution_evidence": sum(1 for item in execution_evidence if item["status"] == "verified"),
            "pending_execution_evidence": len(pending_evidence),
            "failed_execution_evidence": sum(1 for item in execution_evidence if item["status"] == "failed"),
            "forbidden_terms": len(forbidden_terms),
            "blockers": len(blockers),
            "phase40_status": phase40_status,
            "phase38_status": phase38_status,
            "phase36_status": phase36_status,
            "phase34_status": phase34_status,
            "phase37_status": phase37_status,
        },
    }


def evaluate_staging_acceptance_item(
    item: dict[str, Any],
    project_root: Path,
    *,
    forbidden_terms: list[str],
) -> dict[str, Any]:
    result = evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
    result = {**result, "group": str(item.get("group") or "").strip()}
    if not result["exists"]:
        return result
    path = Path(str(result["path"]))
    if not path.is_absolute():
        path = project_root / path
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized_text = text.lower()
    matched_terms = [term for term in forbidden_terms if term and term.lower() in normalized_text]
    if not matched_terms:
        return {**result, "forbidden_content_matches": []}
    return {
        **result,
        "status": "failed",
        "forbidden_content_matches": matched_terms,
        "summary": "staging acceptance evidence contains forbidden content",
    }


def build_staging_acceptance_decision_report(
    decision_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(decision_payload.get("target_release_tag") or "").strip()
    repo = str(decision_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    forbidden_terms = [str(term).strip() for term in decision_payload.get("forbidden_terms", []) if str(term).strip()]
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in decision_payload["prerequisites"]
    ]
    decision_evidence = [
        evaluate_staging_acceptance_item(item, project_root, forbidden_terms=forbidden_terms)
        for item in decision_payload["decision_evidence"]
    ]
    required_acceptance = [
        evaluate_staging_acceptance_item(item, project_root, forbidden_terms=forbidden_terms)
        for item in decision_payload["required_acceptance"]
    ]
    residual_risks = [
        evaluate_staging_acceptance_item(item, project_root, forbidden_terms=forbidden_terms)
        for item in decision_payload["residual_risks"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    failed_items = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in [*decision_evidence, *required_acceptance, *residual_risks]
        if item["required"] and item["status"] == "failed"
    ]
    pending_decision = [item for item in decision_evidence if item["required"] and item["status"] == "pending"]
    pending_acceptance = [
        item for item in [*required_acceptance, *residual_risks] if item["required"] and item["status"] == "pending"
    ]
    statuses = {item["id"]: str(item.get("actual_status") or "") for item in decision_evidence}
    phase41_status = statuses.get("phase41_execution_evidence", "")
    blockers = [*prerequisite_blockers, *failed_items]
    if blockers:
        status = "blocked"
        decision = "blocked"
    elif phase41_status != "hosted_capture_execution_evidence_validated" or pending_decision:
        status = "awaiting_staging_execution_evidence"
        decision = "wait_for_hosted_evidence"
    elif pending_acceptance:
        status = "awaiting_required_acceptance"
        decision = "wait_for_acceptance"
    else:
        status = "staging_accepted_for_production_planning"
        decision = "go_for_production_planning"
    return {
        "schema_version": "phase42_staging_acceptance_decision.v1",
        "source_schema_version": decision_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "decision": decision,
        "execution_environment": str(decision_payload.get("execution_environment") or "staging"),
        "production_execution_authorized": False,
        "lawyer_review_required": True,
        "no_final_legal_advice": True,
        "prerequisites": prerequisites,
        "decision_evidence": decision_evidence,
        "required_acceptance": required_acceptance,
        "residual_risks": residual_risks,
        "pending_decision_evidence": pending_decision,
        "pending_acceptance": pending_acceptance,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_decision_evidence": len(decision_evidence),
            "verified_decision_evidence": sum(1 for item in decision_evidence if item["status"] == "verified"),
            "pending_decision_evidence": len(pending_decision),
            "total_required_acceptance": len(required_acceptance),
            "verified_required_acceptance": sum(1 for item in required_acceptance if item["status"] == "verified"),
            "pending_acceptance": len(pending_acceptance),
            "total_residual_risks": len(residual_risks),
            "verified_residual_risks": sum(1 for item in residual_risks if item["status"] == "verified"),
            "forbidden_terms": len(forbidden_terms),
            "blockers": len(blockers),
            "phase41_status": phase41_status,
        },
    }


def evaluate_production_cutover_readiness_item(
    item: dict[str, Any],
    project_root: Path,
    *,
    forbidden_terms: list[str],
) -> dict[str, Any]:
    result = evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
    result = {**result, "group": str(item.get("group") or "").strip()}
    if not result["exists"]:
        return result
    path = Path(str(result["path"]))
    if not path.is_absolute():
        path = project_root / path
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized_text = text.lower()
    matched_terms = [term for term in forbidden_terms if term and term.lower() in normalized_text]
    if not matched_terms:
        return {**result, "forbidden_content_matches": []}
    return {
        **result,
        "status": "failed",
        "forbidden_content_matches": matched_terms,
        "summary": "production cutover readiness evidence contains forbidden content",
    }


def evaluate_production_cutover_environment(
    payload: dict[str, Any],
    *,
    environment: dict[str, str],
    include_environment: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    for item in payload.get("required_environment", []):
        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("production cutover environment name is required")
        required = bool(item.get("required", True))
        secret = bool(item.get("secret", False))
        min_length = int(item.get("min_length") or 1)
        expected_value = item.get("expected_value")
        url_required = bool(item.get("url", False))
        if not include_environment:
            checks.append(
                {
                    "name": name,
                    "category": str(item.get("category") or ""),
                    "required": required,
                    "secret": secret,
                    "status": "not_evaluated",
                    "summary": "production environment value was not inspected",
                }
            )
            continue
        value = environment.get(name, "")
        present = bool(value)
        length_ok = len(value) >= min_length if present else False
        url_ok = value.startswith(("https://", "http://")) if url_required and present else not url_required
        expected_ok = str(value).strip().lower() == str(expected_value).strip().lower() if expected_value is not None else True
        verified = (not required or present) and (not present or length_ok) and url_ok and expected_ok
        status = "verified" if verified else "missing"
        check = {
            "name": name,
            "category": str(item.get("category") or ""),
            "required": required,
            "secret": secret,
            "status": status,
            "present": present,
            "meets_min_length": length_ok if secret else None,
            "url_scheme_ok": url_ok if url_required else None,
            "expected_value_matched": expected_ok if expected_value is not None else None,
            "summary": "production environment value is present and valid"
            if status == "verified"
            else "production environment value is missing or invalid",
        }
        checks.append(check)
        if required and status != "verified":
            blockers.append({"id": f"env:{name}", "status": status, "summary": check["summary"]})
    return {
        "included": include_environment,
        "checks": checks,
        "blockers": blockers,
        "summary": "Production cutover environment evaluated without exposing secret values."
        if include_environment
        else "Production cutover environment values were not inspected.",
    }


def build_production_cutover_readiness_report(
    readiness_payload: dict[str, Any],
    *,
    project_root: Path,
    environment: dict[str, str] | None = None,
    include_environment: bool = False,
) -> dict[str, Any]:
    target_tag = str(readiness_payload.get("target_release_tag") or "").strip()
    repo = str(readiness_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    forbidden_terms = [str(term).strip() for term in readiness_payload.get("forbidden_terms", []) if str(term).strip()]
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in readiness_payload["prerequisites"]
    ]
    readiness_evidence = [
        evaluate_production_cutover_readiness_item(item, project_root, forbidden_terms=forbidden_terms)
        for item in readiness_payload["readiness_evidence"]
    ]
    rollback_evidence = [
        evaluate_production_cutover_readiness_item(item, project_root, forbidden_terms=forbidden_terms)
        for item in readiness_payload["rollback_evidence"]
    ]
    environment_report = evaluate_production_cutover_environment(
        readiness_payload,
        environment=environment or {},
        include_environment=include_environment,
    )
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    failed_items = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in [*readiness_evidence, *rollback_evidence]
        if item["required"] and item["status"] == "failed"
    ]
    pending_readiness = [
        item for item in [*readiness_evidence, *rollback_evidence] if item["required"] and item["status"] == "pending"
    ]
    statuses = {item["id"]: str(item.get("actual_status") or "") for item in [*readiness_evidence, *rollback_evidence]}
    phase42_status = statuses.get("phase42_staging_acceptance", "")
    environment_ready = include_environment and not environment_report["blockers"]
    blockers = [*prerequisite_blockers, *failed_items, *environment_report["blockers"]]
    if blockers:
        status = "blocked"
    elif phase42_status != "staging_accepted_for_production_planning":
        status = "awaiting_staging_acceptance"
    elif pending_readiness:
        status = "awaiting_production_readiness_evidence"
    elif not environment_ready:
        status = "awaiting_production_environment_inventory"
    else:
        status = "ready_for_production_cutover_dry_run"
    return {
        "schema_version": "phase43_production_cutover_readiness.v1",
        "source_schema_version": readiness_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(readiness_payload.get("execution_environment") or "production_planning"),
        "production_execution_authorized": False,
        "production_mutation_authorized": False,
        "database_migration_authorized": False,
        "raw_data_upload_authorized": False,
        "lawyer_review_required": True,
        "no_final_legal_advice": True,
        "cutover_dry_run_authorized": status == "ready_for_production_cutover_dry_run",
        "prerequisites": prerequisites,
        "readiness_evidence": readiness_evidence,
        "rollback_evidence": rollback_evidence,
        "production_environment": environment_report,
        "pending_readiness_evidence": pending_readiness,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_readiness_evidence": len(readiness_evidence),
            "verified_readiness_evidence": sum(1 for item in readiness_evidence if item["status"] == "verified"),
            "total_rollback_evidence": len(rollback_evidence),
            "verified_rollback_evidence": sum(1 for item in rollback_evidence if item["status"] == "verified"),
            "pending_readiness_evidence": len(pending_readiness),
            "failed_evidence": sum(1 for item in [*readiness_evidence, *rollback_evidence] if item["status"] == "failed"),
            "environment_checks": len(environment_report["checks"]),
            "environment_included": include_environment,
            "forbidden_terms": len(forbidden_terms),
            "blockers": len(blockers),
            "phase42_status": phase42_status,
        },
    }


def production_cutover_dry_run_step_from_mapping(item: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    step_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    stage = str(item.get("stage") or "").strip()
    owner = str(item.get("owner") or "").strip()
    execution_mode = str(item.get("execution_mode") or "").strip()
    command = item.get("command")
    expected_evidence = str(item.get("expected_evidence") or "").strip()
    blockers: list[dict[str, str]] = []
    if not step_id:
        raise ValueError("production cutover dry-run step id is required")
    if not title:
        raise ValueError(f"{step_id} title is required")
    if stage not in {"preflight", "deployment", "verification", "rollback", "owner_approval"}:
        blockers.append({"id": step_id, "status": "failed", "summary": "dry-run step has unsupported stage"})
    if execution_mode not in {"planned_only", "read_only_dry_run", "manual_approval"}:
        blockers.append({"id": step_id, "status": "failed", "summary": "dry-run step has unsupported execution mode"})
    command_parts: list[str] = []
    if command is not None:
        if not isinstance(command, list) or not command or not all(str(part).strip() for part in command):
            blockers.append({"id": step_id, "status": "failed", "summary": "dry-run command must be a non-empty string array"})
        else:
            command_parts = [str(part) for part in command]
    if execution_mode != "manual_approval" and not command_parts:
        blockers.append({"id": step_id, "status": "failed", "summary": "non-approval dry-run step requires a command"})
    if not expected_evidence:
        blockers.append({"id": step_id, "status": "failed", "summary": "dry-run step expected evidence path is required"})
    planned_only = bool(item.get("planned_only", execution_mode == "planned_only"))
    execution_approved = bool(item.get("execution_approved", False))
    risk_flags = {
        "mutates_production": bool(item.get("mutates_production", False)),
        "database_migration": bool(item.get("database_migration", False)),
        "raw_data_upload": bool(item.get("raw_data_upload", False)),
        "index_mutation": bool(item.get("index_mutation", False)),
        "release_promotion": bool(item.get("release_promotion", False)),
    }
    if execution_approved:
        blockers.append({"id": step_id, "status": "failed", "summary": "Phase 44 must not approve execution"})
    if any(risk_flags.values()) and not planned_only:
        blockers.append({"id": step_id, "status": "failed", "summary": "mutating or promotion steps must remain planned-only"})
    if execution_mode == "read_only_dry_run" and risk_flags["mutates_production"]:
        blockers.append({"id": step_id, "status": "failed", "summary": "read-only dry-run steps must not mutate production"})
    status = "planned_only" if planned_only else "ready_for_read_only_dry_run"
    if execution_mode == "manual_approval":
        status = "requires_manual_approval"
    return {
        "id": step_id,
        "title": title,
        "stage": stage,
        "owner": owner or None,
        "execution_mode": execution_mode,
        "command": command_parts,
        "command_line": " ".join(shlex.quote(part) for part in command_parts) if command_parts else "",
        "expected_evidence": expected_evidence,
        "planned_only": planned_only,
        "execution_approved": execution_approved,
        **risk_flags,
        "status": status,
    }, blockers


def production_cutover_owner_approval_from_mapping(item: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    approval_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    owner = str(item.get("owner") or "").strip()
    expected_evidence = str(item.get("expected_evidence") or "").strip()
    required = bool(item.get("required", True))
    blockers: list[dict[str, str]] = []
    if not approval_id:
        raise ValueError("production cutover owner approval id is required")
    if required and (not title or not owner or not expected_evidence):
        blockers.append({"id": approval_id, "status": "failed", "summary": "owner approval is incomplete"})
    return {
        "id": approval_id,
        "title": title,
        "owner": owner,
        "expected_evidence": expected_evidence,
        "required": required,
        "status": "approval_evidence_expected",
    }, blockers


def production_cutover_rollback_step_from_mapping(item: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    rollback_id = str(item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    owner = str(item.get("owner") or "").strip()
    action = str(item.get("action") or "").strip()
    expected_evidence = str(item.get("expected_evidence") or "").strip()
    planned_only = bool(item.get("planned_only", True))
    execution_approved = bool(item.get("execution_approved", False))
    blockers: list[dict[str, str]] = []
    if not rollback_id:
        raise ValueError("production cutover rollback step id is required")
    if not title or not owner or not action or not expected_evidence:
        blockers.append({"id": rollback_id, "status": "failed", "summary": "rollback step is incomplete"})
    if not planned_only:
        blockers.append({"id": rollback_id, "status": "failed", "summary": "rollback steps must remain planned-only in Phase 44"})
    if execution_approved:
        blockers.append({"id": rollback_id, "status": "failed", "summary": "Phase 44 must not approve rollback execution"})
    return {
        "id": rollback_id,
        "title": title,
        "owner": owner,
        "action": action,
        "expected_evidence": expected_evidence,
        "planned_only": planned_only,
        "execution_approved": execution_approved,
        "status": "planned_only",
    }, blockers


def build_production_cutover_dry_run_report(
    dry_run_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(dry_run_payload.get("target_release_tag") or "").strip()
    repo = str(dry_run_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    forbidden_terms = [str(term).strip() for term in dry_run_payload.get("forbidden_terms", []) if str(term).strip()]
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in dry_run_payload["prerequisites"]
    ]
    readiness_reports = [
        evaluate_production_cutover_readiness_item(item, project_root, forbidden_terms=forbidden_terms)
        for item in dry_run_payload["readiness_reports"]
    ]
    dry_run_steps: list[dict[str, Any]] = []
    step_blockers: list[dict[str, str]] = []
    for item in dry_run_payload["dry_run_steps"]:
        step, blockers = production_cutover_dry_run_step_from_mapping(item)
        dry_run_steps.append(step)
        step_blockers.extend(blockers)
    owner_approvals: list[dict[str, Any]] = []
    approval_blockers: list[dict[str, str]] = []
    for item in dry_run_payload["owner_approvals"]:
        approval, blockers = production_cutover_owner_approval_from_mapping(item)
        owner_approvals.append(approval)
        approval_blockers.extend(blockers)
    rollback_steps: list[dict[str, Any]] = []
    rollback_blockers: list[dict[str, str]] = []
    for item in dry_run_payload["rollback_steps"]:
        rollback_step, blockers = production_cutover_rollback_step_from_mapping(item)
        rollback_steps.append(rollback_step)
        rollback_blockers.extend(blockers)
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    failed_reports = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in readiness_reports
        if item["required"] and item["status"] == "failed"
    ]
    pending_reports = [
        item for item in readiness_reports if item["required"] and item["status"] == "pending"
    ]
    statuses = {item["id"]: str(item.get("actual_status") or "") for item in readiness_reports}
    phase43_status = statuses.get("phase43_production_cutover_readiness", "")
    blockers = [*prerequisite_blockers, *failed_reports, *step_blockers, *approval_blockers, *rollback_blockers]
    if blockers:
        status = "blocked"
    elif phase43_status != "ready_for_production_cutover_dry_run" or pending_reports:
        status = "awaiting_production_cutover_readiness"
    else:
        status = "production_cutover_dry_run_planned"
    return {
        "schema_version": "phase44_production_cutover_dry_run.v1",
        "source_schema_version": dry_run_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "cutover_environment": str(dry_run_payload.get("cutover_environment") or "production"),
        "production_execution_authorized": False,
        "production_mutation_authorized": False,
        "database_migration_authorized": False,
        "raw_data_upload_authorized": False,
        "release_promotion_authorized": False,
        "lawyer_review_required": True,
        "no_final_legal_advice": True,
        "phase45_execution_plan_authorized": status == "production_cutover_dry_run_planned",
        "prerequisites": prerequisites,
        "readiness_reports": readiness_reports,
        "dry_run_steps": dry_run_steps,
        "owner_approvals": owner_approvals,
        "rollback_steps": rollback_steps,
        "pending_readiness_reports": pending_reports,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_readiness_reports": len(readiness_reports),
            "verified_readiness_reports": sum(1 for item in readiness_reports if item["status"] == "verified"),
            "pending_readiness_reports": len(pending_reports),
            "failed_readiness_reports": sum(1 for item in readiness_reports if item["status"] == "failed"),
            "dry_run_steps": len(dry_run_steps),
            "planned_only_steps": sum(1 for item in dry_run_steps if item["planned_only"]),
            "read_only_dry_run_steps": sum(1 for item in dry_run_steps if item["execution_mode"] == "read_only_dry_run"),
            "owner_approvals": len(owner_approvals),
            "rollback_steps": len(rollback_steps),
            "forbidden_terms": len(forbidden_terms),
            "blockers": len(blockers),
            "phase43_status": phase43_status,
        },
    }


def evaluate_hosted_capture_acceptance_evidence(
    item: dict[str, Any],
    project_root: Path,
    *,
    forbidden_terms: list[str],
) -> dict[str, Any]:
    result = evaluate_hosted_staging_validation_item(item, project_root, missing_status="pending")
    if not result["exists"]:
        return result
    path = Path(str(result["path"]))
    if not path.is_absolute():
        path = project_root / path
    text = path.read_text(encoding="utf-8", errors="replace")
    normalized_text = text.lower()
    matched_terms = [term for term in forbidden_terms if term and term.lower() in normalized_text]
    if not matched_terms:
        return {**result, "forbidden_content_matches": []}
    return {
        **result,
        "status": "failed",
        "forbidden_content_matches": matched_terms,
        "summary": "evidence contains forbidden hosted-capture content",
    }


def build_hosted_capture_acceptance_report(
    acceptance_payload: dict[str, Any],
    *,
    project_root: Path,
) -> dict[str, Any]:
    target_tag = str(acceptance_payload.get("target_release_tag") or "").strip()
    repo = str(acceptance_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")
    forbidden_terms = [str(term).strip() for term in acceptance_payload.get("forbidden_terms", []) if str(term).strip()]
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in acceptance_payload["prerequisites"]
    ]
    captured_evidence = [
        evaluate_hosted_capture_acceptance_evidence(item, project_root, forbidden_terms=forbidden_terms)
        for item in acceptance_payload["captured_evidence"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] not in {"verified", "pending"}
    ]
    evidence_failures = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in captured_evidence
        if item["required"] and item["status"] == "failed"
    ]
    pending_evidence = [
        item for item in captured_evidence if item["required"] and item["status"] == "pending"
    ]
    statuses = {item["id"]: str(item.get("actual_status") or "") for item in prerequisites}
    phase36_status = statuses.get("phase36_capture_run", "")
    phase34_status = statuses.get("phase34_backend_db_validation", "")
    blockers = [*prerequisite_blockers, *evidence_failures]
    if blockers:
        status = "blocked"
    elif phase36_status != "hosted_evidence_captured":
        status = "awaiting_hosted_capture_execution"
    elif pending_evidence:
        status = "awaiting_captured_evidence_files"
    elif phase34_status != "backend_db_staging_validated":
        status = "awaiting_phase34_backend_db_validation"
    else:
        status = "hosted_capture_accepted"
    return {
        "schema_version": "phase37_hosted_capture_acceptance.v1",
        "source_schema_version": acceptance_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(acceptance_payload.get("execution_environment") or "staging"),
        "prerequisites": prerequisites,
        "captured_evidence": captured_evidence,
        "pending_captured_evidence": pending_evidence,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "pending_prerequisites": sum(1 for item in prerequisites if item["status"] == "pending"),
            "total_captured_evidence": len(captured_evidence),
            "verified_captured_evidence": sum(1 for item in captured_evidence if item["status"] == "verified"),
            "pending_captured_evidence": len(pending_evidence),
            "failed_captured_evidence": sum(1 for item in captured_evidence if item["status"] == "failed"),
            "forbidden_terms": len(forbidden_terms),
            "blockers": len(blockers),
        },
    }


def command_from_mapping(section: str, item: dict[str, Any]) -> OperationalCommand:
    name = str(item.get("name") or "").strip()
    command = item.get("command")
    evidence = str(item.get("evidence") or "").strip()
    if not name:
        raise ValueError(f"{section} command name is required")
    if not isinstance(command, list) or not command or not all(str(part).strip() for part in command):
        raise ValueError(f"{section}.{name} command must be a non-empty string array")
    if not evidence:
        raise ValueError(f"{section}.{name} evidence is required")
    env = item.get("env")
    return OperationalCommand(
        name=name,
        section=section,
        command=tuple(str(part) for part in command),
        evidence=evidence,
        cadence=str(item["cadence"]).strip() if item.get("cadence") else None,
        requires_production_stack=bool(item.get("requires_production_stack", False)),
        required_for_release=bool(item.get("required_for_release", False)),
        env={str(key): str(value) for key, value in env.items()} if isinstance(env, dict) else None,
    )


def operational_commands(manifest: dict[str, Any], *, section: str | None = None) -> list[OperationalCommand]:
    sections = manifest.get("sections")
    if not isinstance(sections, dict):
        raise ValueError("operational manifest sections must be an object")
    selected_sections = [section] if section else list(sections)
    commands: list[OperationalCommand] = []
    for section_name in selected_sections:
        items = sections.get(section_name)
        if not isinstance(items, list) or not items:
            raise ValueError(f"operational manifest section is missing or empty: {section_name}")
        commands.extend(command_from_mapping(section_name, item) for item in items)
    return commands


def render_command(command: OperationalCommand) -> str:
    prefix = ""
    if command.env:
        prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(command.env.items())) + " "
    return prefix + " ".join(shlex.quote(part) for part in command.command)


def operational_plan(manifest: dict[str, Any], *, section: str | None = None) -> dict[str, Any]:
    commands = operational_commands(manifest, section=section)
    return {
        "schema_version": manifest["schema_version"],
        "section": section or "all",
        "status": "planned",
        "commands": [
            {
                "name": command.name,
                "section": command.section,
                "command": list(command.command),
                "command_line": render_command(command),
                "evidence": command.evidence,
                "cadence": command.cadence,
                "requires_production_stack": command.requires_production_stack,
                "required_for_release": command.required_for_release,
            }
            for command in commands
        ],
    }


def scenario_from_mapping(item: dict[str, Any]) -> LoadScenario:
    name = str(item.get("name") or "").strip()
    method = str(item.get("method") or "GET").strip().upper()
    path = str(item.get("path") or "").strip()
    concurrency = int(item.get("concurrency", 1))
    requests = int(item.get("requests", concurrency))
    max_p95_ms = float(item.get("max_p95_ms", 0))
    max_error_rate = float(item.get("max_error_rate", 0))
    if not name:
        raise ValueError("load scenario name is required")
    if method not in {"GET", "POST"}:
        raise ValueError(f"unsupported load scenario method: {method}")
    if not path.startswith("/"):
        raise ValueError(f"load scenario path must start with '/': {path}")
    if concurrency < 1:
        raise ValueError(f"load scenario {name} concurrency must be >= 1")
    if requests < concurrency:
        raise ValueError(f"load scenario {name} requests must be >= concurrency")
    if max_p95_ms <= 0:
        raise ValueError(f"load scenario {name} max_p95_ms must be positive")
    if not 0 <= max_error_rate <= 1:
        raise ValueError(f"load scenario {name} max_error_rate must be between 0 and 1")
    body = item.get("body")
    headers = item.get("headers")
    return LoadScenario(
        name=name,
        method=method,
        path=path,
        concurrency=concurrency,
        requests=requests,
        max_p95_ms=max_p95_ms,
        max_error_rate=max_error_rate,
        body=body if isinstance(body, dict) else None,
        headers={str(key): str(value) for key, value in headers.items()} if isinstance(headers, dict) else None,
    )


def substitute_tokens(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for key, replacement in replacements.items():
            result = result.replace("{" + key + "}", replacement)
        return result
    if isinstance(value, list):
        return [substitute_tokens(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: substitute_tokens(item, replacements) for key, item in value.items()}
    return value


def percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    if percent == 50:
        return float(statistics.median(values))
    if percent == 95:
        return float(statistics.quantiles(values, n=20, method="inclusive")[18])
    if percent == 99:
        return float(statistics.quantiles(values, n=100, method="inclusive")[98])
    raise ValueError("supported percentiles are 50, 95, and 99")


def summarize_load_results(scenario: LoadScenario, samples: list[dict[str, Any]]) -> dict[str, Any]:
    durations = [float(item["elapsed_ms"]) for item in samples]
    error_count = sum(1 for item in samples if int(item.get("status_code") or 0) >= 400 or item.get("error"))
    request_count = len(samples)
    p95_ms = round(percentile(durations, 95), 3)
    error_rate = round(error_count / max(1, request_count), 6)
    status = "pass" if p95_ms <= scenario.max_p95_ms and error_rate <= scenario.max_error_rate else "fail"
    return {
        "name": scenario.name,
        "method": scenario.method,
        "path": scenario.path,
        "status": status,
        "request_count": request_count,
        "concurrency": scenario.concurrency,
        "success_count": request_count - error_count,
        "error_count": error_count,
        "error_rate": error_rate,
        "latency_ms": {
            "min": round(min(durations), 3) if durations else 0.0,
            "p50": round(percentile(durations, 50), 3),
            "p95": p95_ms,
            "p99": round(percentile(durations, 99), 3),
            "max": round(max(durations), 3) if durations else 0.0,
        },
        "thresholds": {
            "max_p95_ms": scenario.max_p95_ms,
            "max_error_rate": scenario.max_error_rate,
        },
    }


def overall_load_status(summaries: list[dict[str, Any]]) -> str:
    return "pass" if summaries and all(item.get("status") == "pass" for item in summaries) else "fail"
