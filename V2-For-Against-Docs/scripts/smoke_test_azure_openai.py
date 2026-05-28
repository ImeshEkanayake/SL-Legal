#!/usr/bin/env python3
"""Smoke test the configured Azure OpenAI chat deployment.

The script does not print secrets. It loads `.env.azure-openai` by default when
present, sends a tiny request, and prints response metadata plus a short preview.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.llm import AzureChatClient, load_azure_chat_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Azure OpenAI chat completions.")
    parser.add_argument("--env-file", default=str(PROJECT_ROOT / ".env.azure-openai"))
    parser.add_argument("--max-completion-tokens", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_azure_chat_config(args.env_file)
    client = AzureChatClient(config)
    try:
        response = client.complete(
            messages=[
                {
                    "role": "system",
                    "content": "You are a connectivity smoke test. Reply with one short sentence.",
                },
                {
                    "role": "user",
                    "content": "Confirm the SL Legal Assist Azure OpenAI chat deployment is reachable.",
                },
            ],
            max_completion_tokens=args.max_completion_tokens,
        )
    except RuntimeError as exc:
        message = str(exc)
        safe_error = {
            "account_name": config.account_name,
            "deployment_name": config.deployment_name,
            "api_version": config.api_version,
            "ok": False,
            "error": message[:1000],
            "next_action": "Verify that the API key belongs to this Azure AI/OpenAI resource and that the endpoint/deployment/API version match.",
        }
        print(json.dumps(safe_error, indent=2))
        return 1
    content = ""
    choices = response.get("choices") or []
    if choices:
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
    safe = {
        "account_name": config.account_name,
        "deployment_name": config.deployment_name,
        "api_version": config.api_version,
        "ok": True,
        "response_id": response.get("id"),
        "model": response.get("model"),
        "finish_reason": choices[0].get("finish_reason") if choices else None,
        "content_preview": content[:500],
    }
    print(json.dumps(safe, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
