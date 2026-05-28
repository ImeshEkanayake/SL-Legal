from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


MetricLabels = tuple[tuple[str, str], ...]


def monotonic_ms() -> float:
    return time.perf_counter() * 1000.0


def _labels(**labels: str | int | None) -> MetricLabels:
    return tuple(sorted((key, str(value)) for key, value in labels.items() if value is not None))


@dataclass
class LatencySummary:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def observe(self, duration_ms: float) -> None:
        self.count += 1
        self.total_ms += duration_ms
        self.max_ms = max(self.max_ms, duration_ms)

    def snapshot(self) -> dict[str, float | int]:
        average_ms = self.total_ms / self.count if self.count else 0.0
        return {
            "count": self.count,
            "total_ms": round(self.total_ms, 3),
            "average_ms": round(average_ms, 3),
            "max_ms": round(self.max_ms, 3),
        }


class OperationalMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, MetricLabels], int] = defaultdict(int)
        self._latencies: dict[MetricLabels, LatencySummary] = defaultdict(LatencySummary)

    def increment(self, name: str, value: int = 1, **labels: str | int | None) -> None:
        if value < 0:
            raise ValueError("metric increments cannot be negative")
        metric_key = (name, _labels(**labels))
        with self._lock:
            self._counters[metric_key] += value

    def observe_latency(self, duration_ms: float, **labels: str | int | None) -> None:
        if duration_ms < 0:
            raise ValueError("latency duration cannot be negative")
        metric_labels = _labels(**labels)
        with self._lock:
            self._latencies[metric_labels].observe(duration_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters: dict[str, list[dict[str, object]]] = defaultdict(list)
            for (name, labels), value in sorted(self._counters.items()):
                counters[name].append({"labels": dict(labels), "value": value})
            latencies = [
                {"labels": dict(labels), **summary.snapshot()}
                for labels, summary in sorted(self._latencies.items())
            ]
        return {
            "counters": dict(counters),
            "latencies": latencies,
        }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._latencies.clear()


def render_prometheus_text(snapshot: dict[str, Any]) -> str:
    lines = [
        "# HELP sl_legal_http_requests_total Total HTTP requests observed by the API.",
        "# TYPE sl_legal_http_requests_total counter",
    ]
    lines.extend(_render_counter(snapshot, "http_requests_total", "sl_legal_http_requests_total"))
    lines.extend(
        [
            "# HELP sl_legal_http_request_errors_total HTTP requests with 4xx or 5xx status codes.",
            "# TYPE sl_legal_http_request_errors_total counter",
        ]
    )
    lines.extend(_render_counter(snapshot, "http_request_errors_total", "sl_legal_http_request_errors_total"))
    lines.extend(
        [
            "# HELP sl_legal_guardrail_request_body_too_large_total Oversized request-body guardrail rejections.",
            "# TYPE sl_legal_guardrail_request_body_too_large_total counter",
        ]
    )
    lines.extend(
        _render_counter(
            snapshot,
            "guardrail_request_body_too_large_total",
            "sl_legal_guardrail_request_body_too_large_total",
        )
    )
    lines.extend(
        [
            "# HELP sl_legal_guardrail_rate_limit_rejections_total Rate-limit guardrail rejections.",
            "# TYPE sl_legal_guardrail_rate_limit_rejections_total counter",
        ]
    )
    lines.extend(
        _render_counter(
            snapshot,
            "guardrail_rate_limit_rejections_total",
            "sl_legal_guardrail_rate_limit_rejections_total",
        )
    )
    lines.extend(
        [
            "# HELP sl_legal_guardrail_audit_write_failures_total Guardrail audit events that could not be written.",
            "# TYPE sl_legal_guardrail_audit_write_failures_total counter",
        ]
    )
    lines.extend(
        _render_counter(
            snapshot,
            "guardrail_audit_write_failures_total",
            "sl_legal_guardrail_audit_write_failures_total",
        )
    )
    lines.extend(
        [
            "# HELP sl_legal_http_request_latency_ms HTTP request latency summaries in milliseconds.",
            "# TYPE sl_legal_http_request_latency_ms summary",
        ]
    )
    latency_lines: list[str] = []
    average_lines = [
        "# HELP sl_legal_http_request_latency_average_ms Average HTTP request latency in milliseconds.",
        "# TYPE sl_legal_http_request_latency_average_ms gauge",
    ]
    max_lines = [
        "# HELP sl_legal_http_request_latency_max_ms Maximum HTTP request latency in milliseconds.",
        "# TYPE sl_legal_http_request_latency_max_ms gauge",
    ]
    for item in snapshot.get("latencies", []):
        labels = item.get("labels", {})
        if not isinstance(labels, dict):
            continue
        count = int(item.get("count", 0))
        total_ms = float(item.get("total_ms", 0.0))
        average_ms = float(item.get("average_ms", 0.0))
        max_ms = float(item.get("max_ms", 0.0))
        latency_lines.append(f"sl_legal_http_request_latency_ms_count{_format_labels(labels)} {count}")
        latency_lines.append(f"sl_legal_http_request_latency_ms_sum{_format_labels(labels)} {_format_number(total_ms)}")
        average_lines.append(
            f"sl_legal_http_request_latency_average_ms{_format_labels(labels)} {_format_number(average_ms)}"
        )
        max_lines.append(f"sl_legal_http_request_latency_max_ms{_format_labels(labels)} {_format_number(max_ms)}")
    lines.extend(latency_lines)
    lines.extend(average_lines)
    lines.extend(max_lines)
    return "\n".join(lines) + "\n"


def _render_counter(snapshot: dict[str, Any], source_name: str, export_name: str) -> list[str]:
    counters = snapshot.get("counters", {})
    if not isinstance(counters, dict):
        return []
    entries = counters.get(source_name, [])
    if not isinstance(entries, list):
        return []
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        labels = entry.get("labels", {})
        if not isinstance(labels, dict):
            labels = {}
        value = int(entry.get("value", 0))
        lines.append(f"{export_name}{_format_labels(labels)} {value}")
    return lines


def _format_labels(labels: dict[str, object]) -> str:
    if not labels:
        return ""
    parts = [f'{key}="{_escape_label_value(str(value))}"' for key, value in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


METRICS = OperationalMetrics()
