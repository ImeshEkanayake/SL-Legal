from __future__ import annotations

from sl_legal_rag.llm.azure_openai import load_azure_chat_config


def test_env_file_overrides_stale_shell_values(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_OPENAI_ACCOUNT_NAME", "old-account")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "old-deployment")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_COMPLETIONS_URL", "https://old.example/chat")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "old-key")

    env_file = tmp_path / ".env.azure-openai"
    env_file.write_text(
        "\n".join(
            [
                "AZURE_OPENAI_ACCOUNT_NAME=new-account",
                "AZURE_OPENAI_DEPLOYMENT_NAME=new-deployment",
                "AZURE_OPENAI_CHAT_COMPLETIONS_URL=https://new.example/chat",
                "AZURE_OPENAI_API_KEY=new-key",
                "AZURE_OPENAI_API_VERSION=2025-04-01-preview",
                "AZURE_OPENAI_TIMEOUT_SECONDS=360",
            ]
        ),
        encoding="utf-8",
    )

    config = load_azure_chat_config(env_file)

    assert config.account_name == "new-account"
    assert config.deployment_name == "new-deployment"
    assert config.chat_completions_url == "https://new.example/chat"
    assert config.api_key == "new-key"
    assert config.timeout_seconds == 360
