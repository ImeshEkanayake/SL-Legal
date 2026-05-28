from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .models import LegalResearchPack, PackItem, ResearchQueryRequest
from .product_policy import source_reliability_warnings


PACK_SCHEMA_VERSION = "legal_research_pack.v1"


@dataclass(frozen=True)
class ResearchPackContractIssue:
    code: str
    message: str


def estimate_text_tokens(text: str) -> int:
    return max(1, len(text.split()) * 4 // 3)


def estimate_pack_tokens(pack: LegalResearchPack) -> int:
    return sum(item.token_estimate if item.token_estimate is not None else estimate_text_tokens(item.text) for item in pack.items)


def canonical_research_pack_payload(pack: LegalResearchPack) -> dict[str, Any]:
    payload = pack.model_dump(mode="json")
    payload["pack_hash"] = None
    return _sort_json_value(payload)


def research_pack_hash(pack: LegalResearchPack) -> str:
    serialized = json.dumps(canonical_research_pack_payload(pack), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def seal_research_pack(
    pack: LegalResearchPack,
    *,
    parent_pack_id: str | None = None,
    pack_version: int | None = None,
    retrieval_trace: list[dict[str, Any]] | None = None,
) -> LegalResearchPack:
    trace = list(retrieval_trace if retrieval_trace is not None else pack.retrieval_trace)
    if not trace:
        trace = _trace_from_pack_config(pack)
    sealed_items = [
        _seal_pack_item(
            item,
            rank=index,
            pack_trace=trace,
        )
        for index, item in enumerate(pack.items, start=1)
    ]
    sealed = pack.model_copy(
        update={
            "schema_version": PACK_SCHEMA_VERSION,
            "parent_pack_id": parent_pack_id if parent_pack_id is not None else pack.parent_pack_id,
            "pack_version": pack_version if pack_version is not None else pack.pack_version,
            "items": sealed_items,
            "token_count": sum(item.token_estimate or estimate_text_tokens(item.text) for item in sealed_items),
            "source_warnings": sorted(set(source_reliability_warnings(pack.model_copy(update={"items": sealed_items})))),
            "retrieval_trace": trace,
        }
    )
    return sealed.model_copy(update={"pack_hash": research_pack_hash(sealed)})


def validate_research_pack_contract(pack: LegalResearchPack) -> list[ResearchPackContractIssue]:
    sealed = seal_research_pack(pack)
    issues: list[ResearchPackContractIssue] = []

    if pack.pack_hash and pack.pack_hash != sealed.pack_hash:
        issues.append(
            ResearchPackContractIssue(
                code="pack_hash_mismatch",
                message="pack_hash does not match the canonical sealed research-pack payload",
            )
        )
    if sealed.schema_version != PACK_SCHEMA_VERSION:
        issues.append(
            ResearchPackContractIssue(
                code="schema_version_mismatch",
                message=f"research pack schema_version must be {PACK_SCHEMA_VERSION}",
            )
        )
    if sealed.pack_version < 1:
        issues.append(ResearchPackContractIssue(code="invalid_pack_version", message="pack_version must be at least 1"))

    expected_prefix = f"{sealed.pack_id}_item_"
    item_ids = [item.pack_item_id for item in sealed.items]
    duplicate_ids = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
    if duplicate_ids:
        issues.append(
            ResearchPackContractIssue(
                code="duplicate_pack_item_id",
                message=f"pack item IDs must be unique: {', '.join(duplicate_ids)}",
            )
        )
    for index, item in enumerate(sealed.items, start=1):
        expected_id = f"{expected_prefix}{index:03d}"
        if item.pack_item_id != expected_id:
            issues.append(
                ResearchPackContractIssue(
                    code="non_canonical_pack_item_id",
                    message=f"pack item {index} must use stable ID {expected_id}",
                )
            )
        if not item.citation.strip():
            issues.append(
                ResearchPackContractIssue(
                    code="missing_citation",
                    message=f"{item.pack_item_id} must include a citation string",
                )
            )
        if not item.text.strip():
            issues.append(
                ResearchPackContractIssue(
                    code="empty_selected_text",
                    message=f"{item.pack_item_id} must include selected text",
                )
            )
        if item.token_estimate is None or item.token_estimate <= 0:
            issues.append(
                ResearchPackContractIssue(
                    code="missing_token_estimate",
                    message=f"{item.pack_item_id} must include a positive token estimate",
                )
            )
        if not item.retrieval_trace:
            issues.append(
                ResearchPackContractIssue(
                    code="missing_item_retrieval_trace",
                    message=f"{item.pack_item_id} must include retrieval trace evidence",
                )
            )

    if sealed.token_count is None or sealed.token_count != estimate_pack_tokens(sealed):
        issues.append(
            ResearchPackContractIssue(
                code="token_count_mismatch",
                message="pack token_count must match selected item token estimates",
            )
        )
    max_tokens = int(sealed.retrieval_config.get("max_tokens") or 0)
    if max_tokens and (sealed.token_count or 0) > max_tokens:
        issues.append(
            ResearchPackContractIssue(
                code="token_budget_exceeded",
                message=f"pack token_count {sealed.token_count} exceeds max_tokens {max_tokens}",
            )
        )
    if sealed.items and not sealed.retrieval_trace:
        issues.append(
            ResearchPackContractIssue(
                code="missing_pack_retrieval_trace",
                message="research pack must include a pack-level retrieval trace",
            )
        )
    if not sealed.items and not sealed.missing_source_summary:
        issues.append(
            ResearchPackContractIssue(
                code="empty_pack_without_missing_source_warning",
                message="empty research packs must explain the retrieval or corpus gap",
            )
        )
    return issues


def require_valid_research_pack_contract(pack: LegalResearchPack) -> LegalResearchPack:
    sealed = seal_research_pack(pack)
    issues = validate_research_pack_contract(sealed)
    if issues:
        details = "; ".join(f"{issue.code}: {issue.message}" for issue in issues)
        raise ValueError("Research pack failed contract validation: " + details)
    return sealed


def build_expansion_query_request(
    *,
    parent_pack: LegalResearchPack,
    query: str,
    max_pack_items: int | None = None,
    max_pack_tokens: int | None = None,
) -> ResearchQueryRequest:
    return ResearchQueryRequest(
        query=query,
        query_class=parent_pack.query_class,
        filters=parent_pack.filters,
        max_pack_items=max_pack_items or max(1, len(parent_pack.items)),
        max_pack_tokens=max_pack_tokens or int(parent_pack.retrieval_config.get("max_tokens") or 12000),
        parent_pack_id=parent_pack.pack_id,
        purpose="pack_expansion",
    )


def _seal_pack_item(item: PackItem, *, rank: int, pack_trace: list[dict[str, Any]]) -> PackItem:
    metadata = dict(item.metadata or {})
    retrieval_evidence = metadata.get("retrieval_evidence") or []
    item_trace = list(item.retrieval_trace)
    if not item_trace:
        item_trace = [
            {
                "stage": "candidate_selection",
                "rank": rank,
                "retrieval_evidence": retrieval_evidence,
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
            }
        ]
    scoring_breakdown = dict(item.scoring_breakdown or {})
    scoring_breakdown.update(
        {
            "fused_score": item.fused_score,
            "authority_level": item.authority_level,
            "source_quality_flags": list(metadata.get("quality_flags", [])),
        }
    )
    if retrieval_evidence:
        scoring_breakdown["retrieval_evidence"] = retrieval_evidence
    return item.model_copy(
        update={
            "token_estimate": item.token_estimate if item.token_estimate is not None else estimate_text_tokens(item.text),
            "retrieval_trace": item_trace or pack_trace,
            "scoring_breakdown": scoring_breakdown,
        }
    )


def _trace_from_pack_config(pack: LegalResearchPack) -> list[dict[str, Any]]:
    retriever_counts = pack.retrieval_config.get("retriever_counts") or {}
    trace: list[dict[str, Any]] = [
        {
            "stage": "request",
            "query_class": pack.query_class.value,
            "filters": pack.filters.model_dump(mode="json"),
            "max_tokens": pack.retrieval_config.get("max_tokens"),
        }
    ]
    if retriever_counts:
        trace.append({"stage": "candidate_retrieval", "retriever_counts": dict(retriever_counts)})
    fusion = pack.retrieval_config.get("fusion")
    if fusion:
        trace.append({"stage": "fusion", "method": fusion, "selected_items": len(pack.items)})
    if pack.missing_source_summary:
        trace.append({"stage": "missing_source_warning", "summary": pack.missing_source_summary})
    return trace


def _sort_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sort_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sort_json_value(item) for item in value]
    return value
