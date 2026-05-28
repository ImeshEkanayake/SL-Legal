#!/usr/bin/env python3
"""Smoke test pack-bounded legal strategy generation against Azure OpenAI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK = PROJECT_ROOT / "data" / "indexes" / "sample_hybrid_research_pack.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "indexes" / "sample_pack_bounded_strategy.json"
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sl_legal_rag.llm import AzureChatClient, load_azure_chat_config  # noqa: E402
from sl_legal_rag.models import LegalResearchPack  # noqa: E402
from sl_legal_rag.strategy import generate_strategy_draft  # noqa: E402


DEFAULT_FACTS = (
    "The client is a trade union with about 45% membership among the workmen. "
    "The employer refused to bargain and suspended union office bearers after complaints about working conditions."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a pack-bounded strategy smoke test.")
    parser.add_argument("--pack", default=str(DEFAULT_PACK))
    parser.add_argument("--facts", default=DEFAULT_FACTS)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack_path = Path(args.pack)
    if not pack_path.is_absolute():
        pack_path = PROJECT_ROOT / pack_path
    pack = LegalResearchPack.model_validate_json(pack_path.read_text(encoding="utf-8"))
    client = AzureChatClient(load_azure_chat_config(PROJECT_ROOT / ".env.azure-openai"))
    draft = generate_strategy_draft(case_facts=args.facts, pack=pack, client=client)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(draft.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.relative_to(PROJECT_ROOT)),
                "pack_id": draft.pack_id,
                "claims": len(draft.claims),
                "missing_authorities": len(draft.missing_authorities),
                "warnings": len(draft.warnings),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
