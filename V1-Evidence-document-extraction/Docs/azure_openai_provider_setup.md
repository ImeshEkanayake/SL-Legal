# Azure OpenAI Provider Setup

The LLM provider integration reads credentials from a local env file and does
not hardcode secrets in source code.

## Local Env File

The local file is:

```text
.env.azure-openai
```

It is ignored by `.gitignore` and should remain `0600`.

Required variables:

```text
AZURE_OPENAI_ACCOUNT_NAME=
AZURE_OPENAI_DEPLOYMENT_NAME=
AZURE_OPENAI_CHAT_COMPLETIONS_URL=
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_API_KEY=
```

## Connectivity Verification

```bash
python3 scripts/smoke_test_azure_openai.py
```

## Current Status

The current Azure OpenAI deployment has been verified through the local provider
client. The verification command returns `ok: true` and reports the deployed
model metadata without printing secrets.
