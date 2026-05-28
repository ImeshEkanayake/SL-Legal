from __future__ import annotations

import pytest

from sl_legal_rag.case_structure import (
    generate_case_structure,
    source_span_coverage_ratio,
    validate_mece_structure_completeness,
    validate_source_spans,
)
from sl_legal_rag.llm import extract_json_object
from sl_legal_rag.models import LegalResearchPack, MeceCaseStructure
from sl_legal_rag.strategy import build_strategy_json_prompt, generate_strategy_draft


class FakeJsonClient:
    def __init__(self, payload):
        self.payloads = payload if isinstance(payload, list) else [payload]
        self.calls = 0

    def complete_json(self, **_kwargs):
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return payload


def minimal_pack() -> LegalResearchPack:
    return LegalResearchPack.model_validate(
        {
            "pack_id": "pack_test",
            "query": "trade union bargaining",
            "query_class": "general_research",
            "filters": {},
            "retrieval_config": {},
            "items": [
                {
                    "pack_item_id": "pack_test_item_001",
                    "chunk_id": "chunk_1",
                    "document_id": "doc_1",
                    "title": "Industrial Disputes Amendment",
                    "document_type": "Act",
                    "source_id": "PARL_ACTS",
                    "authority_level": 2,
                    "citation": "Industrial Disputes (Amendment), No. 56 of 1999",
                    "text": "An employer shall not refuse to bargain with a qualifying trade union.",
                    "fused_score": 1.0,
                    "selection_reason": "test",
                }
            ],
        }
    )


def test_extract_json_object_accepts_fenced_json():
    assert extract_json_object('```json\n{"ok": true}\n```') == {"ok": True}


def test_strategy_generation_rejects_out_of_pack_citation():
    client = FakeJsonClient(
        {
            "pack_id": "pack_test",
            "answer": "This cites an unknown item. [pack_item_999]",
            "claims": [{"claim": "Unsupported claim", "pack_item_ids": ["pack_item_999"]}],
        }
    )

    with pytest.raises(ValueError, match="pack-boundary validation"):
        generate_strategy_draft(case_facts="The employer refused to bargain.", pack=minimal_pack(), client=client)


def test_strategy_prompt_exposes_source_quality_metadata():
    pack = minimal_pack()
    item = pack.items[0].model_copy(
        update={
            "metadata": {
                "quality_flags": ["low_confidence_ocr", "machine_translation_unreviewed"],
                "text_origin": "translation",
                "source_language": "Sinhala",
                "translated_from_language": "Sinhala",
                "translation_review_status": "machine_draft",
            },
            "scoring_breakdown": {"legal_quality_multiplier": 0.5},
        }
    )
    pack = pack.model_copy(update={"items": [item], "source_warnings": ["Sinhala fallback translation used."]})

    messages = build_strategy_json_prompt("The employer refused to bargain.", pack)
    user_prompt = messages[1]["content"]

    assert "text_origin: translation" in user_prompt
    assert "source_language: Sinhala" in user_prompt
    assert "translation_review_status: machine_draft" in user_prompt
    assert "quality_flags: low_confidence_ocr, machine_translation_unreviewed" in user_prompt
    assert "source_quality_notice" in user_prompt
    assert "Sinhala fallback translation used." in user_prompt


def test_source_span_validation_flags_non_exact_quote():
    structure = MeceCaseStructure.model_validate(
        {
            "raw_input_sha256": "abc",
            "case_summary": "summary",
            "facts": [
                {
                    "fact_id": "fact_001",
                    "fact_text": "Employer refused to bargain.",
                    "fact_category": "material_fact",
                    "certainty_label": "explicitly_stated",
                    "source_spans": [{"start_char": 0, "end_char": 8, "quote": "not present"}],
                }
            ],
        }
    )

    warnings = validate_source_spans("Employer refused to bargain.", structure)

    assert warnings


def test_source_span_validation_repairs_exact_quote_offsets():
    structure = MeceCaseStructure.model_validate(
        {
            "raw_input_sha256": "abc",
            "case_summary": "summary",
            "facts": [
                {
                    "fact_id": "fact_001",
                    "fact_text": "Employer refused to bargain.",
                    "fact_category": "material_fact",
                    "certainty_label": "explicitly_stated",
                    "source_spans": [{"start_char": 0, "end_char": 8, "quote": "refused to bargain"}],
                }
            ],
        }
    )

    warnings = validate_source_spans("Employer refused to bargain.", structure)

    assert warnings == []
    assert structure.facts[0].source_spans[0].start_char == 9
    assert structure.facts[0].source_spans[0].end_char == 27


def test_mece_structure_normalizes_observation_objects_and_authority_labels():
    structure = MeceCaseStructure.model_validate(
        {
            "raw_input_sha256": "abc",
            "case_summary": "summary",
            "missing_information": [{"item": "Employer name", "certainty_label": "missing"}],
            "ambiguities": ["around 45% is approximate"],
            "retrieval_queries": [
                {
                    "query": "industrial disputes trade union bargaining",
                    "purpose": "find law",
                    "filters": {"authority_levels": ["primary", "secondary"]},
                }
            ],
        }
    )

    assert structure.missing_information[0].item == "Employer name"
    assert structure.ambiguities[0].item == "around 45% is approximate"
    assert structure.retrieval_queries[0].filters.authority_levels == [1, 6]


def test_mece_completeness_flags_unknown_supporting_fact_and_missing_inference_reason():
    structure = MeceCaseStructure.model_validate(
        {
            "raw_input_sha256": "abc",
            "case_summary": "summary",
            "facts": [
                {
                    "fact_id": "fact_001",
                    "fact_text": "Employer refused to bargain.",
                    "fact_category": "material_fact",
                    "certainty_label": "explicitly_stated",
                    "source_spans": [{"start_char": 9, "end_char": 27, "quote": "refused to bargain"}],
                }
            ],
            "issues": [
                {
                    "issue_id": "issue_001",
                    "issue_text": "Whether refusal to bargain is prohibited.",
                    "issue_type": "statutory_issue",
                    "certainty_label": "inferred",
                    "supporting_fact_ids": ["fact_404"],
                }
            ],
        }
    )

    warnings = validate_mece_structure_completeness("Employer refused to bargain.", structure)

    assert any("unknown supporting facts" in warning for warning in warnings)
    assert any("inferred_reason" in warning for warning in warnings)


def test_mece_source_span_coverage_ratio_uses_corrected_offsets():
    raw_input = "Employer refused to bargain after workers requested union representation."
    structure = MeceCaseStructure.model_validate(
        {
            "raw_input_sha256": "abc",
            "case_summary": "summary",
            "facts": [
                {
                    "fact_id": "fact_001",
                    "fact_text": "Workers requested union representation.",
                    "fact_category": "material_fact",
                    "certainty_label": "explicitly_stated",
                    "source_spans": [{"start_char": 0, "end_char": 7, "quote": "workers requested union representation"}],
                }
            ],
        }
    )

    assert validate_source_spans(raw_input, structure) == []
    assert source_span_coverage_ratio(raw_input, structure) > 0.45


def test_mece_generation_repairs_blocking_completeness_warnings():
    raw_input = (
        "The employer refused to bargain after the union submitted a written request. "
        "The refusal happened on 12 March 2024 and the employee was suspended the next day."
    )
    incomplete = {
        "raw_input_sha256": "old",
        "case_summary": "summary",
        "facts": [
            {
                "fact_id": "fact_001",
                "fact_text": "Employer refused to bargain.",
                "fact_category": "material_fact",
                "certainty_label": "explicitly_stated",
                "source_spans": [],
            }
        ],
        "issues": [
            {
                "issue_id": "issue_001",
                "issue_text": "Whether refusal to bargain is prohibited.",
                "issue_type": "statutory_issue",
                "certainty_label": "inferred",
                "supporting_fact_ids": ["fact_001"],
            }
        ],
    }
    repaired = {
        "raw_input_sha256": "old",
        "case_summary": "summary",
        "facts": [
            {
                "fact_id": "fact_001",
                "fact_text": raw_input,
                "fact_category": "material_fact",
                "certainty_label": "explicitly_stated",
                "source_spans": [{"start_char": 0, "end_char": len(raw_input), "quote": raw_input}],
            }
        ],
        "issues": [
            {
                "issue_id": "issue_001",
                "issue_text": "Whether the refusal to bargain was unlawful.",
                "issue_type": "statutory_issue",
                "certainty_label": "inferred",
                "inferred_reason": "The raw input states that an employer refused to bargain with a union.",
                "supporting_fact_ids": ["fact_001"],
            }
        ],
        "retrieval_queries": [
            {
                "query": "Sri Lanka employer refusal to bargain union",
                "purpose": "Find governing authority.",
                "filters": {},
            }
        ],
    }
    client = FakeJsonClient([incomplete, repaired])

    structure = generate_case_structure(raw_input=raw_input, client=client)

    assert client.calls == 2
    assert structure.facts[0].source_spans[0].quote == raw_input


def test_mece_generation_fails_after_unrepaired_completeness_warnings():
    raw_input = "The employer refused to bargain after the union submitted a written request." * 3
    client = FakeJsonClient(
        {
            "raw_input_sha256": "old",
            "case_summary": "summary",
            "facts": [],
            "retrieval_queries": [],
        }
    )

    with pytest.raises(ValueError, match="completeness validation"):
        generate_case_structure(raw_input=raw_input, client=client)
