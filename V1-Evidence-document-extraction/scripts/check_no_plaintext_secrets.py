#!/usr/bin/env python3
"""Fail when likely plaintext credentials are committed to source files."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCLUDED_DIRS = {
    ".codex_deps",
    ".git",
    ".next",
    ".pytest_cache",
    "__pycache__",
    "coverage",
    "data",
    "data_tracking",
    "dist",
    "logs",
    "node_modules",
}
DEFAULT_INCLUDED_SUFFIXES = {
    ".example",
    ".json",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
MAX_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class SecretPattern:
    name: str
    pattern: re.Pattern[str]


SECRET_PATTERNS = (
    SecretPattern(
        "assigned_api_key",
        re.compile(r"(?i)\b(api[_-]?key|secret|token)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-+/=]{32,}"),
    ),
    SecretPattern(
        "azure_openai_key_shape",
        re.compile(r"\b[A-Za-z0-9]{8,}[A-Za-z0-9+/]{20,}AAAA[A-Za-z0-9+/]{10,}\b"),
    ),
    SecretPattern(
        "bearer_token",
        re.compile(r"(?i)\bauthorization\b\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._\-]{24,}"),
    ),
    SecretPattern(
        "private_key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    ),
)


ALLOWLIST_PATTERNS = (
    re.compile(r"AZURE_OPENAI_API_KEY=$"),
    re.compile(r"TEST_AUTH_SECRET\s*="),
    re.compile(r"test-auth-secret-for-sl-legal-assist"),
    re.compile(r"metrics-token-for-production-scrape-32"),
    re.compile(r"change-this-local-dev-password"),
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    return parser.parse_args(argv)


def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in DEFAULT_EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if path.name.startswith("tmp_"):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        if path.suffix not in DEFAULT_INCLUDED_SUFFIXES and path.name not in {".gitignore", ".env.example"}:
            continue
        yield path


def is_allowlisted(line: str) -> bool:
    return any(pattern.search(line) for pattern in ALLOWLIST_PATTERNS)


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return findings
    for line_number, line in enumerate(lines, start=1):
        if is_allowlisted(line):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.pattern.search(line):
                findings.append(f"{path}:{line_number}: possible {pattern.name}")
    return findings


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    findings: list[str] = []
    for path in iter_source_files(root):
        findings.extend(scan_file(path))
    if findings:
        print("Plaintext secret scan failed:", file=sys.stderr)
        for finding in findings:
            print(finding, file=sys.stderr)
        return 1
    print("Plaintext secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
