#!/usr/bin/env python3
"""Run the Phase 6 production API load scenarios against a local or staging API."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAG_ROOT = PROJECT_ROOT / "rag"
if str(RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(RAG_ROOT))

from sl_legal_rag.operations import (  # noqa: E402
    load_scenarios,
    overall_load_status,
    substitute_tokens,
    summarize_load_results,
)


DEFAULT_SCENARIO = PROJECT_ROOT / "rag" / "evals" / "phase6_load_scenarios.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "logs" / "load-tests" / "phase6-load-report.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("SL_LEGAL_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--scenario", default=str(DEFAULT_SCENARIO))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--user-id", default=os.getenv("SL_LEGAL_LOAD_TEST_USER_ID", os.getenv("SL_LEGAL_USER_ID", "")))
    parser.add_argument("--secret", default=os.getenv("SL_LEGAL_AUTH_HMAC_SECRET", ""))
    parser.add_argument("--case-id", default=os.getenv("SL_LEGAL_LOAD_TEST_CASE_ID", "case_smoke"))
    parser.add_argument("--pack-id", default=os.getenv("SL_LEGAL_LOAD_TEST_PACK_ID", "pack_smoke_001"))
    parser.add_argument("--pack-item-id", default=os.getenv("SL_LEGAL_LOAD_TEST_PACK_ITEM_ID", "pack_item_smoke_001"))
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the scenario plan without making HTTP requests.")
    parser.add_argument("--allow-failures", action="store_true", help="Write the report but return success even if thresholds fail.")
    args = parser.parse_args(argv)
    if not args.dry_run and not args.user_id:
        parser.error("--user-id or SL_LEGAL_LOAD_TEST_USER_ID is required outside dry-run mode")
    if not args.dry_run and len(args.secret) < 32:
        parser.error("--secret or SL_LEGAL_AUTH_HMAC_SECRET must be at least 32 characters outside dry-run mode")
    return args


def signed_headers(*, method: str, path: str, query: str, body: bytes, user_id: str, secret: str) -> dict[str, str]:
    body_sha256 = hashlib.sha256(body).hexdigest()
    timestamp = str(int(time.time()))
    payload = "\n".join([method, path, query, user_id, timestamp, body_sha256])
    signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Accept": "application/json",
        "X-SL-Legal-User-ID": user_id,
        "X-SL-Legal-Auth-Timestamp": timestamp,
        "X-SL-Legal-Auth-Signature": signature,
        "X-SL-Legal-Body-SHA256": body_sha256,
    }


def run_one_request(*, base_url: str, scenario: Any, replacements: dict[str, str], user_id: str, secret: str) -> dict[str, Any]:
    path = str(substitute_tokens(scenario.path, replacements))
    body_payload = substitute_tokens(scenario.body, replacements) if scenario.body is not None else None
    body = json.dumps(body_payload).encode("utf-8") if body_payload is not None else b""
    headers = signed_headers(method=scenario.method, path=path, query="", body=body, user_id=user_id, secret=secret)
    if body:
        headers["Content-Type"] = "application/json"
    if scenario.headers:
        headers.update(scenario.headers)
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body if body else None,
        headers=headers,
        method=scenario.method,
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
            status_code = int(response.status)
            error = None
    except urllib.error.HTTPError as exc:
        exc.read()
        status_code = int(exc.code)
        error = f"HTTPError: {exc.code}"
    except Exception as exc:  # noqa: BLE001
        status_code = 0
        error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "scenario": scenario.name,
        "status_code": status_code,
        "elapsed_ms": round(elapsed_ms, 3),
        "error": error,
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    scenario_path = Path(args.scenario)
    if not scenario_path.is_absolute():
        scenario_path = PROJECT_ROOT / scenario_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    scenarios = load_scenarios(scenario_path)
    replacements = {
        "case_id": args.case_id,
        "pack_id": args.pack_id,
        "pack_item_id": args.pack_item_id,
    }
    plan = [
        {
            "name": scenario.name,
            "method": scenario.method,
            "path": substitute_tokens(scenario.path, replacements),
            "concurrency": scenario.concurrency,
            "requests": scenario.requests,
            "thresholds": {
                "max_p95_ms": scenario.max_p95_ms,
                "max_error_rate": scenario.max_error_rate,
            },
        }
        for scenario in scenarios
    ]
    if args.dry_run:
        print(json.dumps({"status": "planned", "base_url": args.base_url, "scenarios": plan}, indent=2))
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenario_summaries: list[dict[str, Any]] = []
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for scenario in scenarios:
        samples: list[dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=scenario.concurrency) as executor:
            futures = [
                executor.submit(
                    run_one_request,
                    base_url=args.base_url,
                    scenario=scenario,
                    replacements=replacements,
                    user_id=args.user_id,
                    secret=args.secret,
                )
                for _ in range(scenario.requests)
            ]
            for future in concurrent.futures.as_completed(futures):
                samples.append(future.result())
        summary = summarize_load_results(scenario, samples)
        summary["samples"] = sorted(samples, key=lambda item: item["elapsed_ms"], reverse=True)[:10]
        scenario_summaries.append(summary)

    report = {
        "schema_version": "phase6_load_report.v1",
        "status": overall_load_status(scenario_summaries),
        "started_at": started_at,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_url": args.base_url,
        "scenario_file": str(scenario_path.relative_to(PROJECT_ROOT) if scenario_path.is_relative_to(PROJECT_ROOT) else scenario_path),
        "scenarios": scenario_summaries,
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    compact = {key: value for key, value in report.items() if key != "scenarios"}
    compact["output_path"] = str(output_path.relative_to(PROJECT_ROOT) if output_path.is_relative_to(PROJECT_ROOT) else output_path)
    compact["scenario_statuses"] = {item["name"]: item["status"] for item in scenario_summaries}
    print(json.dumps(compact, indent=2))
    return 0 if report["status"] == "pass" or args.allow_failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
