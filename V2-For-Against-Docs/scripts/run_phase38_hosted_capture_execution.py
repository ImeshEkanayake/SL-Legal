#!/usr/bin/env python3
"""Run the Phase 38 hosted capture execution orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_phase36_hosted_evidence_capture import (  # noqa: E402
    DEFAULT_TIMEOUT_SECONDS,
    HttpClient,
    HttpCaptureResponse,
    run_capture_runner,
    urllib_http_client,
)
from sl_legal_rag.operations import (  # noqa: E402
    build_backend_db_staging_validation_report,
    build_hosted_capture_acceptance_report,
    build_hosted_evidence_capture_plan,
    evaluate_hosted_staging_validation_item,
    load_backend_db_staging_validation_manifest,
    load_hosted_capture_acceptance_manifest,
    load_hosted_capture_execution_manifest,
    load_hosted_evidence_capture_manifest,
    load_hosted_evidence_capture_runner_manifest,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase38_hosted_capture_execution.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "readiness" / "phase38-hosted-capture-execution.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-environment", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str, *, project_root: Path | None = None) -> Path:
    path = Path(path_value)
    root = project_root or PROJECT_ROOT
    return path if path.is_absolute() else root / path


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def output_path(manifest: dict[str, Any], key: str, *, project_root: Path) -> Path:
    outputs = manifest.get("report_outputs") or {}
    value = str(outputs.get(key) or "").strip()
    if not value:
        raise ValueError(f"phase38 report_outputs must contain {key}")
    return resolve_path(value, project_root=project_root)


def status_blocker(report_id: str, report: dict[str, Any]) -> dict[str, str] | None:
    status = str(report.get("status") or "")
    if status != "blocked":
        return None
    return {
        "id": report_id,
        "status": "blocked",
        "summary": f"{report_id} returned blocked",
    }


def run_hosted_capture_execution(
    *,
    phase38_payload: dict[str, Any],
    project_root: Path,
    environment: dict[str, str],
    include_environment: bool,
    execute: bool,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    http_client: HttpClient = urllib_http_client,
) -> dict[str, Any]:
    target_tag = str(phase38_payload.get("target_release_tag") or "").strip()
    repo = str(phase38_payload.get("repo") or "").strip()
    if not target_tag:
        raise ValueError("target_release_tag is required")
    if not repo:
        raise ValueError("repo is required")

    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in phase38_payload["prerequisites"]
    ]
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]

    phase35_payload = load_hosted_evidence_capture_manifest(
        project_root / "rag" / "evals" / "phase35_hosted_evidence_capture.json"
    )
    phase36_payload = load_hosted_evidence_capture_runner_manifest(
        project_root / "rag" / "evals" / "phase36_hosted_evidence_capture_runner.json"
    )
    phase34_payload = load_backend_db_staging_validation_manifest(
        project_root / "rag" / "evals" / "phase34_backend_db_staging_validation.json"
    )
    phase37_payload = load_hosted_capture_acceptance_manifest(
        project_root / "rag" / "evals" / "phase37_hosted_capture_acceptance.json"
    )

    phase34_seed_report = build_backend_db_staging_validation_report(phase34_payload, project_root=project_root)
    write_report(
        output_path(phase38_payload, "phase34_backend_db_validation", project_root=project_root),
        phase34_seed_report,
    )

    phase35_report = build_hosted_evidence_capture_plan(
        phase35_payload,
        project_root=project_root,
        environment=environment,
        include_environment=include_environment,
    )
    write_report(output_path(phase38_payload, "phase35_capture_plan", project_root=project_root), phase35_report)

    phase36_report = run_capture_runner(
        runner_payload=phase36_payload,
        capture_payload=phase35_payload,
        project_root=project_root,
        environment=environment,
        include_environment=include_environment,
        execute=execute,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )
    write_report(output_path(phase38_payload, "phase36_capture_run", project_root=project_root), phase36_report)

    phase34_report = build_backend_db_staging_validation_report(phase34_payload, project_root=project_root)
    write_report(output_path(phase38_payload, "phase34_backend_db_validation", project_root=project_root), phase34_report)

    phase37_report = build_hosted_capture_acceptance_report(phase37_payload, project_root=project_root)
    write_report(output_path(phase38_payload, "phase37_capture_acceptance", project_root=project_root), phase37_report)

    blockers = list(prerequisite_blockers)
    for report_id, report in [
        ("phase35_capture_plan", phase35_report),
        ("phase36_capture_run", phase36_report),
    ]:
        blocker = status_blocker(report_id, report)
        if blocker:
            blockers.append(blocker)
    if execute:
        for report_id, report in [
            ("phase34_backend_db_validation", phase34_report),
            ("phase37_capture_acceptance", phase37_report),
        ]:
            blocker = status_blocker(report_id, report)
            if blocker:
                blockers.append(blocker)

    phase35_status = str(phase35_report.get("status") or "")
    phase36_status = str(phase36_report.get("status") or "")
    phase34_status = str(phase34_report.get("status") or "")
    phase37_status = str(phase37_report.get("status") or "")

    if blockers:
        status = "blocked"
    elif execute and phase36_status != "hosted_evidence_captured":
        status = "blocked"
        blockers.append(
            {
                "id": "phase36_capture_run",
                "status": phase36_status,
                "summary": "Phase 36 must capture hosted evidence during execution",
            }
        )
    elif execute and phase34_status != "backend_db_staging_validated":
        status = "hosted_capture_executed_pending_backend_db_validation"
    elif execute and phase37_status != "hosted_capture_accepted":
        status = "hosted_capture_executed_pending_acceptance"
    elif execute:
        status = "hosted_capture_execution_accepted"
    elif phase35_status == "ready_for_capture_execution" and phase36_status == "ready_for_hosted_capture_execution":
        status = "ready_for_hosted_capture_execution"
    else:
        status = "awaiting_hosted_capture_configuration"

    chain = [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "mode": str(item.get("mode") or ""),
            "writes_database": bool(item.get("writes_database", False)),
            "write_classification": item.get("write_classification"),
            "output": str((phase38_payload.get("report_outputs") or {}).get(str(item.get("output_key") or ""), "")),
        }
        for item in phase38_payload["execution_chain"]
    ]
    return {
        "schema_version": "phase38_hosted_capture_execution.v1",
        "source_schema_version": phase38_payload["schema_version"],
        "repo": repo,
        "target_release_tag": target_tag,
        "status": status,
        "execution_environment": str(phase38_payload.get("execution_environment") or "staging"),
        "execute": execute,
        "environment_included": include_environment,
        "prerequisites": prerequisites,
        "execution_chain": chain,
        "phase35_capture_plan": phase35_report,
        "phase36_capture_run": phase36_report,
        "phase34_backend_db_validation": phase34_report,
        "phase37_capture_acceptance": phase37_report,
        "blockers": blockers,
        "summary": {
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "total_prerequisites": len(prerequisites),
            "phase35_status": phase35_status,
            "phase36_status": phase36_status,
            "phase34_status": phase34_status,
            "phase37_status": phase37_status,
            "captured_evidence": phase36_report.get("summary", {}).get("captured_evidence", 0),
            "blockers": len(blockers),
        },
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    manifest = load_hosted_capture_execution_manifest(resolve_path(args.manifest))
    report = run_hosted_capture_execution(
        phase38_payload=manifest,
        project_root=PROJECT_ROOT,
        environment=dict(os.environ) if args.include_environment else {},
        include_environment=args.include_environment,
        execute=args.execute,
        timeout_seconds=args.timeout_seconds,
    )
    output = resolve_path(args.output)
    write_report(output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    expected_statuses = set(manifest.get("success_statuses") or [])
    return 0 if args.allow_blocked or report["status"] in expected_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
