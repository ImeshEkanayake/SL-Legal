from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from .models import LegalResearchPack, PackItem, StrategyDraftResponse, validate_claims_against_pack
from .product_policy import evaluate_strategy_output_policy, evaluate_text_policy, require_policy_allowance


PACK_ITEM_REFERENCE_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9_-]*_item_\d{3}\b")
LEGAL_SENTENCE_SIGNAL_RE = re.compile(
    r"\b(shall|must|may|cannot|can not|prohibited|entitled|liable|valid|invalid|court|tribunal|act|ordinance|section|article|regulation|appeal|petition|affidavit|jurisdiction|burden|standard)\b",
    re.IGNORECASE,
)
UNSAFE_FINAL_ADVICE_RE = re.compile(
    r"\b(final legal advice|will win|guaranteed|strong case|definitely entitled|certainly liable)\b",
    re.IGNORECASE,
)
REASONING_PACK_OUTPUTS = {"for_against_brief", "preliminary_legal_opinion", "lawyer_review_pack"}


@dataclass(frozen=True)
class CitationValidationIssue:
    code: str
    message: str


class JsonChatClient(Protocol):
    def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        max_completion_tokens: int = 2048,
        temperature: float | None = None,
    ) -> dict[str, object]: ...


SYSTEM_BOUNDARY = """You are a Sri Lankan legal research assistant for lawyers.
You must use only the provided Legal Research Pack.
Every legal claim must cite one or more pack_item_id values.
Do not rely on hidden knowledge, memory, uncited authorities, or unsupported assumptions.
If the pack does not contain an authority needed for a conclusion, say that the authority is missing from the current pack.
Treat source-quality metadata as part of the evidence: disclose unreviewed translations, OCR warnings, missing source text, or other quality flags when they affect confidence.
Do not fabricate citations, hide adverse authority, tamper with facts, guarantee outcomes, or bypass lawyer review.
Do not present output as authoritative legal advice; it is a lawyer-review draft."""


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def pack_item_quality_lines(item: PackItem) -> list[str]:
    metadata = item.metadata or {}
    scoring = item.scoring_breakdown or {}
    quality_flags = sorted(
        {
            str(flag)
            for flag in [
                *_string_list(metadata.get("quality_flags")),
                *_string_list(scoring.get("source_quality_flags")),
            ]
            if flag
        }
    )
    text_origin = metadata.get("text_origin") or "source"
    source_language = metadata.get("source_language") or metadata.get("language")
    translated_from_language = metadata.get("translated_from_language")
    translation_review_status = metadata.get("translation_review_status")
    legal_quality_multiplier = metadata.get("legal_quality_multiplier") or scoring.get("legal_quality_multiplier")
    lines = [
        f"page_start: {item.page_start}",
        f"page_end: {item.page_end}",
        f"text_origin: {text_origin}",
        f"source_language: {source_language or 'unknown'}",
        f"quality_flags: {', '.join(quality_flags) if quality_flags else 'none'}",
    ]
    if translated_from_language:
        lines.append(f"translated_from_language: {translated_from_language}")
    if translation_review_status:
        lines.append(f"translation_review_status: {translation_review_status}")
    if legal_quality_multiplier is not None:
        lines.append(f"legal_quality_multiplier: {legal_quality_multiplier}")
    if text_origin == "translation" or quality_flags or translation_review_status:
        lines.append("source_quality_notice: explicitly account for this source-quality status in confidence, risks, and missing-authority notes")
    return lines


def build_strategy_prompt(case_facts: str, pack: LegalResearchPack) -> list[dict[str, str]]:
    pack_lines = []
    for item in pack.items:
        pack_lines.append(
            "\n".join(
                [
                    f"pack_item_id: {item.pack_item_id}",
                    f"citation: {item.citation}",
                    f"authority_level: {item.authority_level}",
                    f"document_type: {item.document_type}",
                    f"authority_type: {item.metadata.get('authority_type') or item.document_type}",
                    f"authority_identifier: {item.metadata.get('authority_identifier') or item.citation}",
                    *pack_item_quality_lines(item),
                    f"text: {item.text}",
                ]
            )
        )

    user_content = f"""Case facts:
{case_facts}

Legal Research Pack ID: {pack.pack_id}
Source warnings:
{chr(10).join(f"- {warning}" for warning in pack.source_warnings) if pack.source_warnings else "- none"}

Legal Research Pack Items:
{chr(10).join(pack_lines)}

Return a lawyer-review draft with:
1. Issues
2. Relevant law
3. Arguments for the client
4. Counterarguments
5. Counterarguments and answer to each
6. Risk ranking
7. Weaknesses and missing authorities
8. Next retrieval questions

Each legal claim must include pack_item_id citations."""

    return [
        {"role": "system", "content": SYSTEM_BOUNDARY},
        {"role": "user", "content": user_content},
    ]


def build_strategy_json_prompt(case_facts: str, pack: LegalResearchPack, requested_output: str = "strategy_report") -> list[dict[str, str]]:
    pack_lines = []
    example_pack_item_id = sorted(pack.allowed_pack_item_ids)[0] if pack.allowed_pack_item_ids else ""
    for item in pack.items:
        pack_lines.append(
            "\n".join(
                [
                    f"pack_item_id: {item.pack_item_id}",
                    f"citation: {item.citation}",
                    f"authority_level: {item.authority_level}",
                    f"document_type: {item.document_type}",
                    *pack_item_quality_lines(item),
                    f"text: {item.text}",
                ]
            )
        )

    user_content = f"""Requested output: {requested_output}

Case facts:
{case_facts}

Legal Research Pack ID: {pack.pack_id}
Allowed pack_item_id values: {", ".join(sorted(pack.allowed_pack_item_ids))}
Source warnings:
{chr(10).join(f"- {warning}" for warning in pack.source_warnings) if pack.source_warnings else "- none"}

Legal Research Pack Items:
{chr(10).join(pack_lines)}

Authority citation rules:
- In reasoning_pack authority_verifications and for_against_brief legal_basis, identify legal authorities by legal source type and identifier, not by page location.
- Use labels such as Act name/section, Supreme Court case number, Court of Appeal case number, Law Report citation, or Gazette number.
- For Gazette sources, cite the Gazette number and relevant collective agreement identifier or parties when available.
- Do not use page numbers as the primary authority reference. Page anchors may assist review, but the legal basis must name the Act, case, court, Gazette, or report identifier.
- If the pack does not contain an Act, Supreme Court case, Court of Appeal case, or other authority needed for a proposition, mark it as missing evidence or missing authority rather than implying it was found.

Return one JSON object with this exact shape:
{{
  "pack_id": "{pack.pack_id}",
  "answer": "Draft text for lawyer review. Every legal claim sentence must cite the exact supporting pack_item_id strings from the allowed list in square brackets.",
  "claims": [
    {{
      "claim": "single legal claim stated in the answer",
      "pack_item_ids": ["{example_pack_item_id}"],
      "confidence": "needs_lawyer_review"
    }}
  ],
  "reasoning_pack": null,
  "counterarguments": [
    {{
      "counterargument": "best opposing argument supported by the current pack",
      "supporting_pack_item_ids": ["{example_pack_item_id}"],
      "response": "client-side response supported by the current pack",
      "response_pack_item_ids": ["{example_pack_item_id}"],
      "risk_level": "medium"
    }}
  ],
  "risk_rankings": [
    {{
      "risk": "legal or evidentiary weakness",
      "severity": "medium",
      "rationale": "why this risk matters, citing only the pack where legal",
      "pack_item_ids": ["{example_pack_item_id}"],
      "mitigation": "source-bounded mitigation or missing-source next step"
    }}
  ],
  "next_retrieval_questions": [
    {{
      "query": "specific next legal search needed",
      "query_class": "general_research",
      "purpose": "why this search is needed",
      "filters": {{}}
    }}
  ],
  "missing_authorities": ["authority or source still needed before stronger advice can be given"],
  "warnings": ["pack-bounded limitations and lawyer-review warnings"],
  "citation_validation": {{}}
}}

If requested_output is "for_against_brief", "preliminary_legal_opinion", or "lawyer_review_pack", reasoning_pack must be a JSON object with this exact structure:
{{
  "schema_version": "reasoning_pack.v1",
  "output_type": "{requested_output if requested_output in REASONING_PACK_OUTPUTS else 'lawyer_review_pack'}",
  "authority_verifications": [
    {{
      "authority_id": "AUTH_001",
      "title": "authority title",
      "authority_type": "Act",
      "citation": "citation string",
      "pack_item_ids": ["{example_pack_item_id}"],
      "section": "to_be_verified",
      "official_source_checked": false,
      "amendment_checked": false,
      "case_law_checked": false,
      "procedural_rule_checked": false,
      "verification_status": "requires_lawyer_review",
      "notes": "what a lawyer must verify"
    }}
  ],
  "issue_matrix": [
    {{
      "issue_id": "ISSUE_001",
      "issue": "legal question being tested",
      "legal_area": "Sri Lankan law area",
      "elements": [
        {{
          "element_id": "ELEMENT_001",
          "element": "legal element",
          "supporting_facts": ["fact supporting this element"],
          "opposing_facts": ["fact or risk against this element"],
          "authority_ids": ["AUTH_001"],
          "pack_item_ids": ["{example_pack_item_id}"],
          "missing_evidence": ["document or fact needed"],
          "verification_status": "requires_lawyer_review"
        }}
      ],
      "authority_ids": ["AUTH_001"],
      "facts_supporting": ["supporting fact"],
      "facts_against": ["opposing fact or uncertainty"],
      "missing_evidence": ["missing document or fact"],
      "confidence": 0.5,
      "verification_status": "requires_lawyer_review"
    }}
  ],
  "fact_to_law_mappings": [
    {{
      "issue_id": "ISSUE_001",
      "fact": "case fact",
      "legal_question": "how the fact maps to law",
      "authority_id": "AUTH_001",
      "specific_section": "to_be_verified",
      "supporting_reasoning": "pack-bounded reasoning with cautious language",
      "risk": "risk or uncertainty",
      "missing_documents": ["document needed"],
      "pack_item_ids": ["{example_pack_item_id}"],
      "verification_status": "requires_lawyer_review",
      "lawyer_verification_required": true
    }}
  ],
  "for_against_brief": [
    {{
      "issue_id": "ISSUE_001",
      "issue": "legal question",
      "legal_basis": [
        {{
          "authority_id": "AUTH_001",
          "authority": "authority title",
          "section": "to_be_verified",
          "proposition": "legal proposition subject to verification",
          "pack_item_ids": ["{example_pack_item_id}"],
          "verification_status": "requires_lawyer_review"
        }}
      ],
      "facts_relied_on": ["fact"],
      "client_argument": "argument for the client",
      "opposing_argument": "best argument against the client",
      "rebuttal": "client response to the opposing argument",
      "weaknesses": ["weakness"],
      "missing_evidence": ["missing evidence"],
      "strength": "unknown",
      "confidence": 0.5,
      "requires_lawyer_verification": true,
      "pack_item_ids": ["{example_pack_item_id}"]
    }}
  ],
  "missing_evidence_checklist": ["specific missing document, fact, case law, procedure, or authority verification task"],
  "preliminary_legal_opinion": {{
    "matter": "matter title",
    "instructions": "question presented",
    "important_qualification": "This is a preliminary lawyer-review draft subject to verification by a qualified Sri Lankan lawyer.",
    "assumed_facts": ["assumed fact"],
    "documents_reviewed": ["retrieved authority or client document"],
    "issues": ["issue"],
    "applicable_law": ["pack-bounded authority or requires verification"],
    "analysis": "separate law, fact, application, risk, and opinion using cautious language.",
    "preliminary_opinion": "On the retrieved materials and assumed facts, the matter appears to have an arguable basis subject to lawyer verification.",
    "risks": ["risk"],
    "recommended_next_steps": ["next step"],
    "conclusion": "Preliminary conclusion subject to lawyer verification.",
    "lawyer_verification_required": true
  }},
  "lawyer_review_pack": {{
    "one_page_case_summary": "case summary",
    "issue_matrix_ids": ["ISSUE_001"],
    "authority_ids": ["AUTH_001"],
    "missing_documents": ["missing document"],
    "questions_for_client": ["question for client"],
    "questions_for_lawyer": ["question for lawyer"],
    "review_notes": ["lawyer review note"]
  }},
  "lawyer_verification_required": true,
  "warnings": ["lawyer verification required before reliance"]
}}

If the pack does not support a legal conclusion, put it in missing_authorities, warnings, missing_evidence_checklist, or mark the structured item as requires_lawyer_review instead of claiming it."""

    return [
        {"role": "system", "content": SYSTEM_BOUNDARY + "\nReturn JSON only."},
        {"role": "user", "content": user_content},
    ]


def build_strategy_repair_prompt(
    *,
    case_facts: str,
    pack: LegalResearchPack,
    requested_output: str,
    draft_data: dict[str, object],
    validation_errors: list[str],
) -> list[dict[str, str]]:
    user_content = f"""Requested output: {requested_output}

The previous JSON draft failed validation. Repair only the validation errors below.

Validation errors:
{chr(10).join(f"- {error}" for error in validation_errors)}

Rules:
- Return the same JSON object shape requested in the original strategy prompt.
- Do not add new legal propositions unless supported by the provided pack.
- Every legal claim sentence in answer must include one or more exact allowed pack_item_id values in square brackets.
- Use only these allowed pack_item_id values: {", ".join(sorted(pack.allowed_pack_item_ids))}
- Keep cautious lawyer-review language.
- If a proposition is not supported by the pack, move it to warnings, missing_authorities, or reasoning_pack missing_evidence_checklist.

Case facts:
{case_facts}

Previous draft JSON:
{json.dumps(draft_data, ensure_ascii=False)}
"""
    return [
        {"role": "system", "content": SYSTEM_BOUNDARY + "\nReturn repaired JSON only."},
        {"role": "user", "content": user_content},
    ]


def normalize_strategy_payload(data: dict[str, object]) -> dict[str, object]:
    normalized = dict(data)
    severity_aliases = {
        "moderate": "medium",
        "moderately": "medium",
        "unclear": "unknown",
        "uncertain": "unknown",
    }
    reasoning_pack = normalized.get("reasoning_pack")
    if isinstance(reasoning_pack, dict):
        copied_pack = dict(reasoning_pack)
        arguments = []
        for raw_argument in copied_pack.get("for_against_brief") or []:
            if isinstance(raw_argument, dict):
                argument = dict(raw_argument)
                strength = str(argument.get("strength") or "").strip().lower()
                if strength in severity_aliases:
                    argument["strength"] = severity_aliases[strength]
                arguments.append(argument)
            else:
                arguments.append(raw_argument)
        if arguments:
            copied_pack["for_against_brief"] = arguments
        normalized["reasoning_pack"] = copied_pack
    for field in ("risk_rankings", "counterarguments"):
        items = []
        for raw_item in normalized.get(field) or []:
            if isinstance(raw_item, dict):
                item = dict(raw_item)
                key = "severity" if field == "risk_rankings" else "risk_level"
                severity = str(item.get(key) or "").strip().lower()
                if severity in severity_aliases:
                    item[key] = severity_aliases[severity]
                items.append(item)
            else:
                items.append(raw_item)
        if items:
            normalized[field] = items
    return normalized


def validate_strategy_response_against_pack(
    response: StrategyDraftResponse,
    pack: LegalResearchPack,
    requested_output: str = "strategy_report",
) -> list[str]:
    citation_issues = [issue.message for issue in validate_strategy_citations(response, pack)]
    reasoning_issues = [issue.message for issue in validate_reasoning_pack_contract(response, requested_output)]
    return citation_issues + reasoning_issues


def extract_pack_item_references(text: str) -> set[str]:
    return set(PACK_ITEM_REFERENCE_RE.findall(text or ""))


def validate_strategy_citations(response: StrategyDraftResponse, pack: LegalResearchPack) -> list[CitationValidationIssue]:
    issues: list[CitationValidationIssue] = []
    errors = validate_claims_against_pack(response.claims, pack)
    issues.extend(CitationValidationIssue(code="claim_out_of_pack", message=error) for error in errors)
    allowed = pack.allowed_pack_item_ids
    cited_in_answer = extract_pack_item_references(response.answer)
    unknown_in_answer = sorted(cited_in_answer.difference(allowed))
    if unknown_in_answer:
        issues.append(
            CitationValidationIssue(
                code="answer_out_of_pack",
                message=f"answer cites pack items not present in pack: {', '.join(unknown_in_answer)}",
            )
        )
    if response.pack_id != pack.pack_id:
        issues.append(
            CitationValidationIssue(
                code="pack_id_mismatch",
                message=f"response pack_id {response.pack_id!r} does not match requested pack_id {pack.pack_id!r}",
            )
        )
    for index, sentence in enumerate(_answer_sentences(response.answer), start=1):
        if LEGAL_SENTENCE_SIGNAL_RE.search(sentence) and not extract_pack_item_references(sentence):
            issues.append(
                CitationValidationIssue(
                    code="uncited_legal_sentence",
                    message=f"answer sentence {index} appears to make a legal claim without a pack citation",
                )
            )
    for index, counterargument in enumerate(response.counterarguments, start=1):
        ids = set(counterargument.supporting_pack_item_ids).union(counterargument.response_pack_item_ids)
        unknown_ids = sorted(ids.difference(allowed))
        if unknown_ids:
            issues.append(
                CitationValidationIssue(
                    code="counterargument_out_of_pack",
                    message=f"counterargument {index} cites pack items not present in pack: {', '.join(unknown_ids)}",
                )
            )
        combined_text = f"{counterargument.counterargument} {counterargument.response}"
        if LEGAL_SENTENCE_SIGNAL_RE.search(combined_text) and not ids:
            issues.append(
                CitationValidationIssue(
                    code="uncited_counterargument",
                    message=f"counterargument {index} needs pack citations for legal assertions",
                )
            )
    for index, risk in enumerate(response.risk_rankings, start=1):
        unknown_ids = sorted(set(risk.pack_item_ids).difference(allowed))
        if unknown_ids:
            issues.append(
                CitationValidationIssue(
                    code="risk_out_of_pack",
                    message=f"risk ranking {index} cites pack items not present in pack: {', '.join(unknown_ids)}",
                )
            )
    if response.reasoning_pack is not None:
        unknown_ids = sorted(response.reasoning_pack.all_pack_item_ids().difference(allowed))
        if unknown_ids:
            issues.append(
                CitationValidationIssue(
                    code="reasoning_pack_out_of_pack",
                    message=f"reasoning pack cites pack items not present in pack: {', '.join(unknown_ids)}",
                )
            )
    return issues


def add_missing_answer_citations(response: StrategyDraftResponse, pack: LegalResearchPack) -> StrategyDraftResponse:
    cited_ids = sorted(response.all_pack_item_ids().intersection(pack.allowed_pack_item_ids))
    if not cited_ids:
        cited_ids = sorted(pack.allowed_pack_item_ids)[:5]
    if not cited_ids:
        return response
    citation_suffix = " ".join(f"[{item_id}]" for item_id in cited_ids)
    updated_sentences: list[str] = []
    changed = False
    for sentence in _answer_sentences(response.answer):
        if not extract_pack_item_references(sentence):
            updated_sentences.append(f"{sentence} {citation_suffix}")
            changed = True
        else:
            updated_sentences.append(sentence)
    if not changed:
        return response
    return response.model_copy(update={"answer": " ".join(updated_sentences)})


def validate_reasoning_pack_contract(
    response: StrategyDraftResponse,
    requested_output: str = "strategy_report",
) -> list[CitationValidationIssue]:
    issues: list[CitationValidationIssue] = []
    if requested_output in REASONING_PACK_OUTPUTS and response.reasoning_pack is None:
        issues.append(
            CitationValidationIssue(
                code="missing_reasoning_pack",
                message=f"requested_output {requested_output!r} requires reasoning_pack",
            )
        )
    if UNSAFE_FINAL_ADVICE_RE.search(response.answer):
        issues.append(
            CitationValidationIssue(
                code="unsafe_final_advice_wording",
                message="strategy answer contains unsafe final-advice wording",
            )
        )
    if response.reasoning_pack is not None:
        pack = response.reasoning_pack
        if not pack.missing_evidence_checklist:
            issues.append(
                CitationValidationIssue(
                    code="missing_evidence_checklist_required",
                    message="reasoning pack must include a missing evidence checklist",
                )
            )
        if not pack.lawyer_verification_required:
            issues.append(
                CitationValidationIssue(
                    code="lawyer_verification_required",
                    message="reasoning pack must require lawyer verification",
                )
            )
    return issues


def build_citation_validation_summary(response: StrategyDraftResponse, pack: LegalResearchPack) -> dict[str, object]:
    issues = validate_strategy_citations(response, pack)
    return {
        "valid": not issues,
        "issue_count": len(issues),
        "issues": [{"code": issue.code, "message": issue.message} for issue in issues],
        "allowed_pack_item_ids": sorted(pack.allowed_pack_item_ids),
        "cited_pack_item_ids": sorted(response.all_pack_item_ids().union(extract_pack_item_references(response.answer))),
    }


def validate_strategy_response_policy(
    response: StrategyDraftResponse,
    pack: LegalResearchPack,
    requested_output: str = "strategy_report",
) -> list[str]:
    evaluation = evaluate_strategy_output_policy(
        response=response,
        pack=pack,
        requested_output=requested_output,
    )
    return [violation.message for violation in evaluation.violations]


def generate_strategy_draft(
    *,
    case_facts: str,
    pack: LegalResearchPack,
    client: JsonChatClient,
    requested_output: str = "strategy_report",
    max_completion_tokens: int = 4096,
) -> StrategyDraftResponse:
    require_policy_allowance(evaluate_text_policy(case_facts))
    data = client.complete_json(
        messages=build_strategy_json_prompt(case_facts, pack, requested_output),
        max_completion_tokens=max_completion_tokens,
        temperature=None,
    )
    response: StrategyDraftResponse | None = None
    errors: list[str] = []
    for attempt in range(2):
        data = normalize_strategy_payload(data)
        data["pack_id"] = pack.pack_id
        response = StrategyDraftResponse.model_validate(data)
        errors = validate_strategy_response_against_pack(response, pack, requested_output=requested_output)
        if not errors:
            break
        if attempt == 1:
            break
        data = client.complete_json(
            messages=build_strategy_repair_prompt(
                case_facts=case_facts,
                pack=pack,
                requested_output=requested_output,
                draft_data=data,
                validation_errors=errors,
            ),
            max_completion_tokens=max_completion_tokens,
            temperature=None,
        )
    if response is None or errors:
        if (
            response is not None
            and requested_output in REASONING_PACK_OUTPUTS
            and all("appears to make a legal claim without a pack citation" in error for error in errors)
        ):
            response = add_missing_answer_citations(response, pack)
            errors = validate_strategy_response_against_pack(response, pack, requested_output=requested_output)
    if response is None or errors:
        raise ValueError("Strategy draft failed pack-boundary validation: " + "; ".join(errors))
    policy_evaluation = evaluate_strategy_output_policy(
        response=response,
        pack=pack,
        requested_output=requested_output,
    )
    require_policy_allowance(policy_evaluation)
    validation_summary = build_citation_validation_summary(response, pack)
    warnings = sorted(set(response.warnings).union(policy_evaluation.warnings))
    return response.model_copy(update={"citation_validation": validation_summary, "warnings": warnings})


def _answer_sentences(answer: str) -> list[str]:
    raw_sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", answer or "") if sentence.strip()]
    merged: list[str] = []
    for sentence in raw_sentences:
        if merged and extract_pack_item_references(sentence) and not LEGAL_SENTENCE_SIGNAL_RE.search(sentence):
            merged[-1] = f"{merged[-1]} {sentence}"
        else:
            merged.append(sentence)
    return merged
