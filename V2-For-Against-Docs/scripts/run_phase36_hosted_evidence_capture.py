#!/usr/bin/env python3
"""Run the Phase 36 hosted evidence capture runner."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import (  # noqa: E402
    build_hosted_evidence_capture_plan,
    evaluate_hosted_staging_validation_item,
    load_hosted_evidence_capture_manifest,
    load_hosted_evidence_capture_runner_manifest,
)


DEFAULT_MANIFEST = PROJECT_ROOT / "rag" / "evals" / "phase36_hosted_evidence_capture_runner.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "readiness" / "phase36-hosted-evidence-capture-run.json"
DEFAULT_TIMEOUT_SECONDS = 15
USER_HEADER = "X-SL-Legal-User-ID"
TIMESTAMP_HEADER = "X-SL-Legal-Auth-Timestamp"
SIGNATURE_HEADER = "X-SL-Legal-Auth-Signature"
BODY_SHA256_HEADER = "X-SL-Legal-Body-SHA256"


@dataclass(frozen=True)
class HttpCaptureResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


HttpClient = Callable[[str, str, dict[str, str], int], HttpCaptureResponse]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-environment", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--allow-blocked", action="store_true")
    return parser.parse_args(argv)


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def urllib_http_client(method: str, url: str, headers: dict[str, str], timeout_seconds: int) -> HttpCaptureResponse:
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return HttpCaptureResponse(
                status_code=int(response.status),
                headers={str(key): str(value) for key, value in response.headers.items()},
                body=response.read(65536),
            )
    except urllib.error.HTTPError as exc:
        return HttpCaptureResponse(
            status_code=int(exc.code),
            headers={str(key): str(value) for key, value in exc.headers.items()},
            body=exc.read(65536),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bool_from_env(environment: dict[str, str], name: str) -> bool:
    return environment.get(name, "").strip().lower() == "true"


def int_from_env(environment: dict[str, str], name: str) -> int:
    value = environment.get(name, "").strip()
    try:
        return int(value)
    except ValueError:
        return -1


def render_task_path(path_template: str, environment: dict[str, str]) -> str:
    replacements = {
        "case_id": urllib.parse.quote(environment.get("SL_LEGAL_STAGING_CASE_ID", ""), safe=""),
        "document_id": urllib.parse.quote(environment.get("SL_LEGAL_STAGING_DOCUMENT_ID", ""), safe=""),
    }
    return path_template.format(**replacements)


def response_expectations_by_task(runner_payload: dict[str, Any]) -> dict[str, list[str]]:
    expectations: dict[str, list[str]] = {}
    for item in runner_payload.get("response_expectations", []):
        task_id = str(item.get("task_id") or "").strip()
        keys = [str(key).strip() for key in item.get("expected_json_keys", []) if str(key).strip()]
        if task_id:
            expectations[task_id] = keys
    return expectations


def parse_json_body(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def signed_headers(*, method: str, path: str, query_string: str, environment: dict[str, str]) -> dict[str, str]:
    body_sha256 = hashlib.sha256(b"").hexdigest()
    timestamp = int(time.time())
    user_id = environment["SL_LEGAL_STAGING_USER_ID"]
    payload = "\n".join([method.upper(), path, query_string, user_id, str(timestamp), body_sha256]).encode("utf-8")
    signature = hmac.new(environment["SL_LEGAL_AUTH_HMAC_SECRET"].encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return {
        USER_HEADER: user_id,
        TIMESTAMP_HEADER: str(timestamp),
        SIGNATURE_HEADER: signature,
        BODY_SHA256_HEADER: body_sha256,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def capture_operator_json(task: dict[str, Any], environment: dict[str, str], *, now_utc: str) -> dict[str, Any]:
    domain_write_count = int_from_env(environment, "SL_LEGAL_PHASE35_DB_DOMAIN_WRITE_COUNT")
    migration_count = int_from_env(environment, "SL_LEGAL_PHASE35_DB_MIGRATION_COUNT")
    raw_data_uploaded = bool_from_env(environment, "SL_LEGAL_PHASE35_RAW_DATA_UPLOADED")
    readonly_confirmed = bool_from_env(environment, "SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED")
    task_id = task["id"]
    if task_id == "db_readonly_health_template":
        return {
            "status": "healthy" if readonly_confirmed and migration_count == 0 else "blocked",
            "access_mode": "read_only" if readonly_confirmed else "unconfirmed",
            "migration_applied": migration_count != 0,
            "captured_at_utc": now_utc,
            "source": "phase36_hosted_evidence_capture_runner",
        }
    if task_id == "db_write_guard_template":
        clean = domain_write_count == 0 and migration_count == 0 and not raw_data_uploaded
        return {
            "status": "no_unintended_writes" if clean else "writes_detected",
            "write_count": max(domain_write_count, 0),
            "migration_count": max(migration_count, 0),
            "raw_data_uploaded": raw_data_uploaded,
            "captured_at_utc": now_utc,
            "source": "phase36_hosted_evidence_capture_runner",
        }
    if task_id == "operator_db_acceptance_template":
        accepted = readonly_confirmed and domain_write_count == 0 and migration_count == 0 and not raw_data_uploaded
        return {
            "status": "accepted" if accepted else "blocked",
            "database_migrated": migration_count != 0,
            "raw_data_uploaded": raw_data_uploaded,
            "writes_reviewed": domain_write_count == 0,
            "captured_at_utc": now_utc,
            "source": "phase36_hosted_evidence_capture_runner",
        }
    return {
        "status": "prepared",
        "captured_at_utc": now_utc,
        "source": "phase36_hosted_evidence_capture_runner",
    }


def capture_http_task(
    task: dict[str, Any],
    *,
    runner_payload: dict[str, Any],
    environment: dict[str, str],
    project_root: Path,
    timeout_seconds: int,
    now_utc: str,
    http_client: HttpClient,
) -> dict[str, Any]:
    method = str(task["method"]).upper()
    path = render_task_path(str(task["path_template"]), environment)
    api_base = environment["SL_LEGAL_STAGING_API_BASE_URL"].rstrip("/")
    url = f"{api_base}{path}"
    split_url = urllib.parse.urlsplit(url)
    headers = {"Accept": "application/json"}
    if task["requires_signed_auth"]:
        headers.update(
            signed_headers(
                method=method,
                path=split_url.path,
                query_string=split_url.query,
                environment=environment,
            )
        )
    response = http_client(method, url, headers, timeout_seconds)
    json_body = parse_json_body(response.body)
    expected_keys = response_expectations_by_task(runner_payload).get(task["id"], [])
    missing_keys = [key for key in expected_keys if not isinstance(json_body, dict) or key not in json_body]
    ok = 200 <= response.status_code < 300 and not missing_keys
    output = resolve_output(project_root, task["evidence_output"])
    if task["id"] == "api_health_capture":
        write_json(
            output,
            {
                "status": "healthy" if ok else "unhealthy",
                "runtime": "hosted_staging",
                "backend": "real",
                "database_connected": bool_from_env(environment, "SL_LEGAL_PHASE35_DB_READONLY_CONFIRMED"),
                "http_status": response.status_code,
                "captured_at_utc": now_utc,
                "source": "phase36_hosted_evidence_capture_runner",
            },
        )
    else:
        json_keys = sorted(json_body.keys()) if isinstance(json_body, dict) else []
        write_log(
            output,
            [
                f"run_id=phase36-{task['id']}",
                f"task_id={task['id']}",
                f"method={method}",
                f"path_template={task['path_template']}",
                f"http_status={response.status_code}",
                f"response_content_type={response.headers.get('content-type', response.headers.get('Content-Type', ''))}",
                f"response_json_keys={','.join(json_keys)}",
                f"expected_json_keys={','.join(expected_keys)}",
                f"missing_json_keys={','.join(missing_keys)}",
                f"write_classification={task.get('write_classification') or 'none'}",
                f"captured_at_utc={now_utc}",
                f"exit_status={0 if ok else 1}",
            ],
        )
    return {
        "id": task["id"],
        "title": task["title"],
        "status": "captured" if ok else "failed",
        "http_status": response.status_code,
        "evidence_output": task["evidence_output"],
        "missing_json_keys": missing_keys,
    }


def resolve_output(project_root: Path, path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else project_root / path


def execute_capture_tasks(
    *,
    runner_payload: dict[str, Any],
    capture_plan: dict[str, Any],
    project_root: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    http_client: HttpClient,
    now_utc: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for task in capture_plan["capture_tasks"]:
        if task["type"] in {"http_check", "signed_http_check"}:
            results.append(
                capture_http_task(
                    task,
                    runner_payload=runner_payload,
                    environment=environment,
                    project_root=project_root,
                    timeout_seconds=timeout_seconds,
                    now_utc=now_utc,
                    http_client=http_client,
                )
            )
            continue
        output = resolve_output(project_root, task["evidence_output"])
        payload = capture_operator_json(task, environment, now_utc=now_utc)
        write_json(output, payload)
        results.append(
            {
                "id": task["id"],
                "title": task["title"],
                "status": "captured" if payload["status"] in {"healthy", "no_unintended_writes", "accepted", "prepared"} else "failed",
                "evidence_output": task["evidence_output"],
            }
        )
    return results


def run_capture_runner(
    *,
    runner_payload: dict[str, Any],
    capture_payload: dict[str, Any],
    project_root: Path,
    environment: dict[str, str],
    include_environment: bool,
    execute: bool,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    http_client: HttpClient = urllib_http_client,
    now_utc: str | None = None,
) -> dict[str, Any]:
    prerequisites = [
        evaluate_hosted_staging_validation_item(item, project_root, missing_status="missing")
        for item in runner_payload["prerequisites"]
    ]
    capture_plan = build_hosted_evidence_capture_plan(
        capture_payload,
        project_root=project_root,
        environment=environment,
        include_environment=include_environment,
    )
    prerequisite_blockers = [
        {"id": item["id"], "status": item["status"], "summary": item["summary"]}
        for item in prerequisites
        if item["required"] and item["status"] != "verified"
    ]
    capture_plan_blockers = [
        {"id": f"capture_plan:{item['id']}", "status": item["status"], "summary": item["summary"]}
        for item in capture_plan["blockers"]
    ]
    blockers = [*prerequisite_blockers, *capture_plan_blockers]
    capture_results: list[dict[str, Any]] = []
    if execute and not include_environment:
        blockers.append(
            {
                "id": "execute_requires_environment",
                "status": "failed",
                "summary": "--execute requires --include-environment",
            }
        )
    if execute and capture_plan["status"] != "ready_for_capture_execution":
        blockers.append(
            {
                "id": "capture_plan_not_ready",
                "status": "failed",
                "summary": "hosted capture plan must be ready_for_capture_execution before capture",
            }
        )
    if not blockers and execute:
        capture_results = execute_capture_tasks(
            runner_payload=runner_payload,
            capture_plan=capture_plan,
            project_root=project_root,
            environment=environment,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
            now_utc=now_utc or utc_now(),
        )
        blockers.extend(
            {
                "id": item["id"],
                "status": item["status"],
                "summary": "hosted capture task failed",
            }
            for item in capture_results
            if item["status"] != "captured"
        )
    if blockers:
        status = "blocked"
    elif execute:
        status = "hosted_evidence_captured"
    elif capture_plan["status"] == "ready_for_capture_execution":
        status = "ready_for_hosted_capture_execution"
    else:
        status = "ready_for_hosted_capture_runner_configuration"
    return {
        "schema_version": "phase36_hosted_evidence_capture_runner.v1",
        "source_schema_version": runner_payload["schema_version"],
        "repo": runner_payload["repo"],
        "target_release_tag": runner_payload["target_release_tag"],
        "status": status,
        "execution_environment": str(runner_payload.get("execution_environment") or "staging"),
        "execute": execute,
        "environment_included": include_environment,
        "prerequisites": prerequisites,
        "capture_plan": capture_plan,
        "capture_results": capture_results,
        "blockers": blockers,
        "summary": {
            "total_prerequisites": len(prerequisites),
            "verified_prerequisites": sum(1 for item in prerequisites if item["status"] == "verified"),
            "capture_tasks": len(capture_plan["capture_tasks"]),
            "captured_evidence": sum(1 for item in capture_results if item["status"] == "captured"),
            "failed_captures": sum(1 for item in capture_results if item["status"] == "failed"),
            "blockers": len(blockers),
        },
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    runner_manifest_path = resolve_path(args.manifest)
    runner_payload = load_hosted_evidence_capture_runner_manifest(runner_manifest_path)
    capture_payload = load_hosted_evidence_capture_manifest(resolve_path(str(runner_payload["capture_manifest_path"])))
    report = run_capture_runner(
        runner_payload=runner_payload,
        capture_payload=capture_payload,
        project_root=PROJECT_ROOT,
        environment=dict(os.environ) if args.include_environment else {},
        include_environment=args.include_environment,
        execute=args.execute,
        timeout_seconds=args.timeout_seconds,
    )
    output = resolve_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    expected_statuses = {
        "ready_for_hosted_capture_runner_configuration",
        "ready_for_hosted_capture_execution",
        "hosted_evidence_captured",
    }
    return 0 if args.allow_blocked or report["status"] in expected_statuses else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
