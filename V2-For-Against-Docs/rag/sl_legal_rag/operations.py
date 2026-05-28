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
