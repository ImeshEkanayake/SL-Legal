from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AzureChatConfig:
    account_name: str
    deployment_name: str
    chat_completions_url: str
    api_key: str
    api_version: str = "2025-04-01-preview"
    timeout_seconds: int = 120


class AzureChatClient:
    """Minimal Azure OpenAI Chat Completions client.

    This uses the deployment-specific URL supplied by Azure and keeps API keys
    outside code. It intentionally returns raw response metadata so callers can
    log model/deployment behavior without logging secrets.
    """

    def __init__(self, config: AzureChatConfig):
        self.config = config

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        max_completion_tokens: int = 512,
        temperature: float | None = None,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": messages,
            "max_completion_tokens": max_completion_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format is not None:
            payload["response_format"] = response_format

        request = urllib.request.Request(
            self.config.chat_completions_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "api-key": self.config.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Azure OpenAI request failed with HTTP {exc.code}: {body}") from exc

    def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        max_completion_tokens: int = 2048,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        response = self.complete(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        choices = response.get("choices") or []
        if not choices:
            raise RuntimeError("Azure OpenAI response did not include choices")
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("Azure OpenAI JSON response was empty")
        return extract_json_object(content)


def extract_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object, accepting fenced JSON when a model returns it."""

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object")
    return parsed


def load_env_file(path: str | Path, *, override: bool = True) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_key = key.strip()
        if override or env_key not in os.environ:
            os.environ[env_key] = value.strip().strip('"').strip("'")


def load_azure_chat_config(
    env_file: str | Path | None = None,
    *,
    override_env_file: bool = True,
) -> AzureChatConfig:
    if env_file is not None:
        load_env_file(env_file, override=override_env_file)

    required = {
        "AZURE_OPENAI_ACCOUNT_NAME": os.getenv("AZURE_OPENAI_ACCOUNT_NAME", ""),
        "AZURE_OPENAI_DEPLOYMENT_NAME": os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", ""),
        "AZURE_OPENAI_CHAT_COMPLETIONS_URL": os.getenv("AZURE_OPENAI_CHAT_COMPLETIONS_URL", ""),
        "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY", ""),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing Azure OpenAI settings: {', '.join(missing)}")

    return AzureChatConfig(
        account_name=required["AZURE_OPENAI_ACCOUNT_NAME"],
        deployment_name=required["AZURE_OPENAI_DEPLOYMENT_NAME"],
        chat_completions_url=required["AZURE_OPENAI_CHAT_COMPLETIONS_URL"],
        api_key=required["AZURE_OPENAI_API_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        timeout_seconds=int(os.getenv("AZURE_OPENAI_TIMEOUT_SECONDS", "120")),
    )
