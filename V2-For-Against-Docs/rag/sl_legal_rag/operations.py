from __future__ import annotations

import json
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


def load_scenarios(path: Path) -> list[LoadScenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("load scenario file must contain a non-empty scenarios array")
    return [scenario_from_mapping(item) for item in scenarios]


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
