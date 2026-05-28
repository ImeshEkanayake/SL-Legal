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


def load_scenarios(path: Path) -> list[LoadScenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("load scenario file must contain a non-empty scenarios array")
    return [scenario_from_mapping(item) for item in scenarios]


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
