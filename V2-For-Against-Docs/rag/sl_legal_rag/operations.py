from __future__ import annotations

import json
import shlex
import statistics
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
