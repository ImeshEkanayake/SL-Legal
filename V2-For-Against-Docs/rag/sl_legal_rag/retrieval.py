from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable
import uuid

from .models import LegalResearchPack, PackItem, QueryClass, RetrievalFilters
from .research_pack import seal_research_pack


AUTHORITY_BOOSTS = {
    1: 1.35,
    2: 1.30,
    3: 1.25,
    4: 1.15,
    5: 1.05,
    6: 1.00,
    7: 0.95,
    8: 0.90,
    9: 0.80,
}

EXACT_CITATION_RRF_BOOST = 0.10


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    title: str
    document_type: str
    source_id: str
    authority_level: int
    citation: str
    text: str
    score: float
    retriever: str
    year: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_url: str | None = None
    local_path: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def reciprocal_rank_fusion(result_sets: Iterable[list[SearchHit]], *, k: int = 60) -> list[SearchHit]:
    """Fuse ranked result lists using RRF, then apply legal authority boosts."""

    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[str]] = defaultdict(list)
    best_hit: dict[str, SearchHit] = {}

    for result_set in result_sets:
        for rank, hit in enumerate(result_set, start=1):
            scores[hit.chunk_id] += 1.0 / (k + rank)
            if hit.metadata.get("exact_citation_match") if hit.metadata else False:
                scores[hit.chunk_id] += EXACT_CITATION_RRF_BOOST / rank
            evidence[hit.chunk_id].append(f"{hit.retriever} rank {rank}")
            previous = best_hit.get(hit.chunk_id)
            if previous is None or hit.score > previous.score:
                best_hit[hit.chunk_id] = hit

    fused: list[SearchHit] = []
    for chunk_id, score in scores.items():
        hit = best_hit[chunk_id]
        authority_boost = AUTHORITY_BOOSTS.get(hit.authority_level, 0.85)
        hit.score = score * authority_boost
        hit.metadata = dict(hit.metadata or {})
        hit.metadata["retrieval_evidence"] = sorted(set(evidence[chunk_id]))
        fused.append(hit)

    return sorted(fused, key=lambda item: item.score, reverse=True)


def select_pack_items(
    hits: list[SearchHit],
    *,
    pack_id: str,
    max_items: int,
    max_tokens: int,
    token_estimator=lambda text: max(1, len(text.split()) * 4 // 3),
) -> list[PackItem]:
    selected: list[PackItem] = []
    used_tokens = 0
    seen_documents: set[str] = set()

    for hit in hits:
        estimate = token_estimator(hit.text)
        if selected and used_tokens + estimate > max_tokens:
            continue
        diversity_note = "high authority"
        if hit.document_id not in seen_documents:
            diversity_note = "new source document"
        seen_documents.add(hit.document_id)
        pack_item_id = f"{pack_id}_item_{len(selected) + 1:03d}"
        evidence = hit.metadata.get("retrieval_evidence", []) if hit.metadata else []
        evidence_text = "; ".join(str(item) for item in evidence) if evidence else hit.retriever
        item_trace = [
            {
                "stage": "candidate_selection",
                "rank": len(selected) + 1,
                "retriever": hit.retriever,
                "retrieval_evidence": evidence,
                "chunk_id": hit.chunk_id,
                "document_id": hit.document_id,
            }
        ]
        selected.append(
            PackItem(
                pack_item_id=pack_item_id,
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                title=hit.title,
                document_type=hit.document_type,
                source_id=hit.source_id,
                authority_level=hit.authority_level,
                year=hit.year,
                citation=hit.citation,
                page_start=hit.page_start,
                page_end=hit.page_end,
                text=hit.text,
                fused_score=round(hit.score, 6),
                selection_reason=f"{evidence_text}; {diversity_note}",
                source_url=hit.source_url,
                local_path=hit.local_path,
                token_estimate=estimate,
                scoring_breakdown={
                    "fused_score": round(hit.score, 6),
                    "authority_level": hit.authority_level,
                    "source_quality_flags": list(hit.metadata.get("quality_flags", [])) if hit.metadata else [],
                    "retrieval_evidence": evidence,
                    "legal_quality_multiplier": hit.metadata.get("legal_quality_multiplier") if hit.metadata else None,
                },
                retrieval_trace=item_trace,
                metadata=hit.metadata,
            )
        )
        used_tokens += estimate
        if len(selected) >= max_items:
            break

    return selected


def legal_quality_multiplier(hit: SearchHit) -> float:
    """Authority and source-quality adjustment for reranked legal search hits."""

    multiplier = AUTHORITY_BOOSTS.get(hit.authority_level, 0.85)
    flags = {str(flag) for flag in hit.metadata.get("quality_flags", [])} if hit.metadata else set()
    if "low_confidence_ocr" in flags or "low_ocr_confidence" in flags:
        multiplier *= 0.70
    if "missing_page_anchor" in flags:
        multiplier *= 0.80
    if "unofficial_source" in flags:
        multiplier *= 0.88
    if "translated_text_fallback" in flags:
        multiplier *= 0.85
    if "machine_translation_unreviewed" in flags:
        multiplier *= 0.75
    if "current_consolidated_law" in flags:
        multiplier *= 1.10
    if "exact_citation_match" in flags or bool(hit.metadata.get("exact_citation_match")):
        multiplier *= 1.25
    return multiplier


def rerank_with_legal_quality(hits: list[SearchHit]) -> list[SearchHit]:
    """Apply explainable legal-quality scoring after neural reranking.

    The neural reranker should set `hit.score` before this function runs. This
    adjustment keeps legally stronger sources from being buried by semantically
    similar but weaker material.
    """

    reranked: list[SearchHit] = []
    for hit in hits:
        multiplier = legal_quality_multiplier(hit)
        hit.score *= multiplier
        hit.metadata = dict(hit.metadata or {})
        hit.metadata["legal_quality_multiplier"] = round(multiplier, 6)
        reranked.append(hit)
    return sorted(reranked, key=lambda item: item.score, reverse=True)


def build_research_pack(
    *,
    query: str,
    query_class: QueryClass,
    filters: RetrievalFilters,
    hits: list[SearchHit],
    max_items: int,
    max_tokens: int,
    missing_source_summary: str | None = None,
) -> LegalResearchPack:
    pack_id = f"pack_{uuid.uuid4().hex}"
    items = select_pack_items(hits, pack_id=pack_id, max_items=max_items, max_tokens=max_tokens)
    pack = LegalResearchPack(
        pack_id=pack_id,
        query=query,
        query_class=query_class,
        filters=filters,
        retrieval_config={
            "fusion": "reciprocal_rank_fusion",
            "authority_boosts": AUTHORITY_BOOSTS,
            "max_items": max_items,
            "max_tokens": max_tokens,
        },
        items=items,
        missing_source_summary=missing_source_summary,
    )
    return seal_research_pack(pack)
