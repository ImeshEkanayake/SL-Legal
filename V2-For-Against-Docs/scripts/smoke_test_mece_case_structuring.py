#!/usr/bin/env python3
"""Smoke test the MECE case structuring agent against Azure OpenAI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.case_structure import generate_case_structure  # noqa: E402
from sl_legal_rag.llm import AzureChatClient, load_azure_chat_config  # noqa: E402


DEFAULT_FACTS = (
    "Our client is a trade union representing around 45% of the workmen at a factory in Colombo. "
    "The employer refused to bargain with the union in March 2024 and later suspended two union office bearers "
    "after they complained about working conditions. We need to know what authorities to research."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an Azure-backed MECE case structuring smoke test.")
    parser.add_argument("--facts", default=DEFAULT_FACTS)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "data" / "indexes" / "sample_mece_case_structure.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = AzureChatClient(load_azure_chat_config(PROJECT_ROOT / ".env.azure-openai"))
    structure = generate_case_structure(raw_input=args.facts, client=client)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(structure.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.relative_to(PROJECT_ROOT)),
                "facts": len(structure.facts),
                "issues": len(structure.issues),
                "retrieval_queries": len(structure.retrieval_queries),
                "warnings": len(structure.warnings),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
