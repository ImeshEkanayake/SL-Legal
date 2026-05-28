from __future__ import annotations

import hashlib
from typing import Protocol

from .models import MeceCaseStructure, SourceSpan


class JsonChatClient(Protocol):
    def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        max_completion_tokens: int = 2048,
        temperature: float | None = None,
    ) -> dict[str, object]: ...


MECE_SYSTEM_PROMPT = """You are the MECE Case Structuring Agent for a Sri Lankan legal research product.
Your job is to structure the user's case facts only. Do not answer legal questions and do not cite legal authorities.

Rules:
- Preserve all information from the raw input by decomposing it into atomic facts, issues, missing information, ambiguities, and contradictions.
- Every fact, party, and timeline event must map back to one or more exact source spans from the raw user input where possible.
- Use certainty labels only from: explicitly_stated, inferred, ambiguous, missing, contradictory.
- If something is inferred, explain why in the issue or fact text; never hide the inference.
- Retrieval queries are retrieval-only prompts for the search layer, not legal conclusions.
- Use as many facts, issues, timeline events, missing-information items, ambiguity items, contradiction items, and retrieval queries as needed to preserve the full raw input. Never drop facts to stay compact.
- Do not repeat the schema, do not explain your method, and do not add markdown.
- Return JSON only."""


BLOCKING_COMPLETENESS_WARNING_SNIPPETS = (
    "duplicate fact IDs",
    "references unknown supporting facts",
    "is inferred but has no inferred_reason",
    "structure contains no non-missing facts",
    "source span coverage is low",
    "structure has facts or issues but no retrieval queries",
    "has no source spans",
    "has no exact source quote",
    "quote is not an exact substring",
    "offsets do not match quote",
)


def raw_input_sha256(raw_input: str) -> str:
    return hashlib.sha256(raw_input.encode("utf-8")).hexdigest()


def build_mece_case_structure_prompt(raw_input: str) -> list[dict[str, str]]:
    expected_hash = raw_input_sha256(raw_input)
    user_prompt = f"""Raw user input source_id: user_input
Raw input SHA-256: {expected_hash}

Raw user input:
{raw_input}

Return one JSON object with this shape:
{{
  "schema_version": "mece_case_structure.v1",
  "source_id": "user_input",
  "raw_input_sha256": "{expected_hash}",
  "case_summary": "neutral one-paragraph factual summary",
  "parties": [
    {{
      "name": "party/person/entity name",
      "role": "client/opponent/employer/employee/court/agency/unknown",
      "certainty_label": "explicitly_stated",
      "source_spans": [{{"source_id": "user_input", "start_char": 0, "end_char": 10, "quote": "exact quote"}}]
    }}
  ],
  "facts": [
    {{
      "fact_id": "fact_001",
      "fact_text": "one atomic fact",
      "fact_category": "material_fact/procedural_fact/evidence_fact/date_fact/party_fact",
      "certainty_label": "explicitly_stated",
      "materiality": "high/medium/low/unknown",
      "disputed_status": "undisputed/disputed/unknown",
      "source_spans": [{{"source_id": "user_input", "start_char": 0, "end_char": 10, "quote": "exact quote"}}]
    }}
  ],
  "timeline": [],
  "issues": [
    {{
      "issue_id": "issue_001",
      "issue_text": "candidate legal or factual issue requiring retrieval",
      "issue_type": "statutory_issue/case_law_issue/procedure/evidence/factual_issue",
      "priority": "high/normal/low",
      "certainty_label": "inferred",
      "inferred_reason": "why this issue follows from the facts",
      "supporting_fact_ids": ["fact_001"]
    }}
  ],
  "missing_information": [],
  "ambiguities": [],
  "contradictions": [],
  "retrieval_queries": [
    {{
      "query": "focused retrieval query",
      "query_class": "general_research",
      "purpose": "why this query is needed",
      "filters": {{"document_types": [], "source_ids": [], "years": [], "language": "English", "authority_levels": [], "require_official": false}}
    }}
  ],
  "warnings": []
}}"""
    return [
        {"role": "system", "content": MECE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_mece_repair_prompt(raw_input: str, previous_json: str, warnings: list[str]) -> list[dict[str, str]]:
    expected_hash = raw_input_sha256(raw_input)
    user_prompt = f"""Raw user input source_id: user_input
Raw input SHA-256: {expected_hash}

Raw user input:
{raw_input}

The previous JSON structure failed completeness validation:
{chr(10).join(f"- {warning}" for warning in warnings)}

Previous JSON:
{previous_json}

Repair the structure. Preserve every stated fact and every relevant uncertainty from the raw input. Add missing atomic facts, source spans, issues, timeline events, and retrieval queries. Source span quotes must be exact substrings of the raw input.

Return the same JSON schema as before, with raw_input_sha256 set to {expected_hash}. Return JSON only."""
    return [
        {"role": "system", "content": MECE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def validate_source_spans(raw_input: str, structure: MeceCaseStructure) -> list[str]:
    warnings: list[str] = []

    def check_span(path: str, span: SourceSpan) -> None:
        if not span.quote:
            warnings.append(f"{path} has no exact source quote")
            return
        found_at = raw_input.find(span.quote)
        if found_at == -1:
            warnings.append(f"{path} quote is not an exact substring of raw input")
            return
        corrected_end = found_at + len(span.quote)
        if span.start_char != found_at or span.end_char != corrected_end:
            span.start_char = found_at
            span.end_char = corrected_end
            return
        if span.start_char is None or span.end_char is None:
            warnings.append(f"{path} is missing character offsets")
            return
        if span.end_char < span.start_char:
            warnings.append(f"{path} has end_char before start_char")
            return
        if raw_input[span.start_char : span.end_char] != span.quote:
            warnings.append(f"{path} offsets do not match quote")

    for index, party in enumerate(structure.parties, start=1):
        for span_index, span in enumerate(party.source_spans, start=1):
            check_span(f"parties[{index}].source_spans[{span_index}]", span)
    for index, fact in enumerate(structure.facts, start=1):
        if fact.certainty_label != "missing" and not fact.source_spans:
            warnings.append(f"facts[{index}] has no source spans")
        for span_index, span in enumerate(fact.source_spans, start=1):
            check_span(f"facts[{index}].source_spans[{span_index}]", span)
    for index, event in enumerate(structure.timeline, start=1):
        for span_index, span in enumerate(event.source_spans, start=1):
            check_span(f"timeline[{index}].source_spans[{span_index}]", span)
    return warnings


def validate_mece_structure_completeness(raw_input: str, structure: MeceCaseStructure) -> list[str]:
    warnings: list[str] = []
    fact_ids = [fact.fact_id for fact in structure.facts]
    duplicate_fact_ids = sorted({fact_id for fact_id in fact_ids if fact_ids.count(fact_id) > 1})
    if duplicate_fact_ids:
        warnings.append("duplicate fact IDs: " + ", ".join(duplicate_fact_ids))

    known_fact_ids = set(fact_ids)
    for index, issue in enumerate(structure.issues, start=1):
        unknown_fact_ids = sorted(set(issue.supporting_fact_ids).difference(known_fact_ids))
        if unknown_fact_ids:
            warnings.append(f"issues[{index}] references unknown supporting facts: {', '.join(unknown_fact_ids)}")
        if issue.certainty_label == "inferred" and not (issue.inferred_reason or "").strip():
            warnings.append(f"issues[{index}] is inferred but has no inferred_reason")

    non_missing_facts = [fact for fact in structure.facts if fact.certainty_label != "missing"]
    if raw_input.strip() and not non_missing_facts:
        warnings.append("structure contains no non-missing facts from non-empty raw input")

    coverage_ratio = source_span_coverage_ratio(raw_input, structure)
    if len(raw_input.strip()) >= 120 and coverage_ratio < 0.35:
        warnings.append(f"source span coverage is low: {coverage_ratio:.2%}")

    if not structure.retrieval_queries and (structure.issues or non_missing_facts):
        warnings.append("structure has facts or issues but no retrieval queries")
    return warnings


def blocking_mece_warnings(warnings: list[str]) -> list[str]:
    return [
        warning
        for warning in warnings
        if any(snippet in warning for snippet in BLOCKING_COMPLETENESS_WARNING_SNIPPETS)
    ]


def validate_mece_structure(raw_input: str, structure: MeceCaseStructure) -> list[str]:
    warnings: list[str] = []
    span_warnings = validate_source_spans(raw_input, structure)
    if span_warnings:
        structure.warnings.extend(span_warnings)
        warnings.extend(span_warnings)
    completeness_warnings = validate_mece_structure_completeness(raw_input, structure)
    if completeness_warnings:
        structure.warnings.extend(completeness_warnings)
        warnings.extend(completeness_warnings)
    return warnings


def source_span_coverage_ratio(raw_input: str, structure: MeceCaseStructure) -> float:
    if not raw_input:
        return 0.0
    covered: set[int] = set()
    spans: list[SourceSpan] = []
    for party in structure.parties:
        spans.extend(party.source_spans)
    for fact in structure.facts:
        spans.extend(fact.source_spans)
    for event in structure.timeline:
        spans.extend(event.source_spans)
    for span in spans:
        if span.start_char is None or span.end_char is None:
            continue
        start = max(0, span.start_char)
        end = min(len(raw_input), span.end_char)
        covered.update(range(start, end))
    return round(len(covered) / len(raw_input), 4)


def generate_case_structure(
    *,
    raw_input: str,
    client: JsonChatClient,
    max_completion_tokens: int = 8192,
    retry_on_incomplete: bool = True,
) -> MeceCaseStructure:
    expected_hash = raw_input_sha256(raw_input)
    data = client.complete_json(
        messages=build_mece_case_structure_prompt(raw_input),
        max_completion_tokens=max_completion_tokens,
        temperature=None,
    )
    data["raw_input_sha256"] = expected_hash
    structure = MeceCaseStructure.model_validate(data)
    warnings = validate_mece_structure(raw_input, structure)
    blocking_warnings = blocking_mece_warnings(warnings)
    if blocking_warnings and retry_on_incomplete:
        repair_data = client.complete_json(
            messages=build_mece_repair_prompt(
                raw_input=raw_input,
                previous_json=structure.model_dump_json(),
                warnings=blocking_warnings,
            ),
            max_completion_tokens=max_completion_tokens,
            temperature=None,
        )
        repair_data["raw_input_sha256"] = expected_hash
        structure = MeceCaseStructure.model_validate(repair_data)
        warnings = validate_mece_structure(raw_input, structure)
        blocking_warnings = blocking_mece_warnings(warnings)
    if blocking_warnings:
        raise ValueError("MECE case structure failed completeness validation: " + "; ".join(blocking_warnings))
    return structure
