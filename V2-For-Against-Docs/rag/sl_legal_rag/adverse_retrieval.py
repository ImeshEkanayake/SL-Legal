from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Iterable

from .retrieval import SearchHit


class RetrievalQueryIntent(str, Enum):
    SUPPORTIVE = "supportive"
    ADVERSE = "adverse"
    LIMITATION = "limitation"
    EXCEPTION = "exception"
    PROCEDURAL_RISK = "procedural_risk"


@dataclass(frozen=True)
class PairedRetrievalQuery:
    query: str
    intent: RetrievalQueryIntent
    purpose: str
    expansion_terms: tuple[str, ...]

    @property
    def query_id(self) -> str:
        return f"{self.intent.value}:{_stable_slug(self.query)}"


INTENT_EXPANSIONS: dict[RetrievalQueryIntent, tuple[str, ...]] = {
    RetrievalQueryIntent.SUPPORTIVE: (
        "supports",
        "establishes",
        "authority",
        "legal basis",
    ),
    RetrievalQueryIntent.ADVERSE: (
        "contrary authority",
        "distinguish",
        "weakens",
        "adverse",
    ),
    RetrievalQueryIntent.LIMITATION: (
        "limitation",
        "barred",
        "time limit",
        "threshold",
    ),
    RetrievalQueryIntent.EXCEPTION: (
        "exception",
        "unless",
        "exemption",
        "qualification",
    ),
    RetrievalQueryIntent.PROCEDURAL_RISK: (
        "burden of proof",
        "jurisdiction",
        "procedure",
        "admissibility",
    ),
}

INTENT_PURPOSES: dict[RetrievalQueryIntent, str] = {
    RetrievalQueryIntent.SUPPORTIVE: "Find authorities that support the client-side claim.",
    RetrievalQueryIntent.ADVERSE: "Find contrary or weakening authorities that must be disclosed to the lawyer.",
    RetrievalQueryIntent.LIMITATION: "Find limitation periods, thresholds, bars, and statutory limits.",
    RetrievalQueryIntent.EXCEPTION: "Find exceptions, qualifications, exemptions, and carve-outs.",
    RetrievalQueryIntent.PROCEDURAL_RISK: "Find burden, procedure, jurisdiction, admissibility, and remedy risks.",
}

ADVERSE_SIGNAL_TERMS = {
    "adverse",
    "against",
    "contrary",
    "distinguish",
    "distinguished",
    "overrule",
    "overruled",
    "barred",
    "limitation",
    "prescription",
    "exception",
    "unless",
    "exempt",
    "qualification",
    "threshold",
    "burden",
    "jurisdiction",
    "procedure",
    "admissibility",
    "delay",
    "waiver",
    "estoppel",
}

SUPPORTIVE_SIGNAL_TERMS = {
    "supports",
    "establishes",
    "entitled",
    "right",
    "shall",
    "must",
    "duty",
    "liable",
    "remedy",
    "relief",
}


def expand_for_against_queries(query: str) -> list[PairedRetrievalQuery]:
    base = " ".join(query.split())
    if not base:
        raise ValueError("query is required")
    variants: list[PairedRetrievalQuery] = []
    for intent in RetrievalQueryIntent:
        expansion_terms = INTENT_EXPANSIONS[intent]
        variants.append(
            PairedRetrievalQuery(
                query=f"{base} {' '.join(expansion_terms)}",
                intent=intent,
                purpose=INTENT_PURPOSES[intent],
                expansion_terms=expansion_terms,
            )
        )
    return variants


def tag_hits_for_query_intent(hits: Iterable[SearchHit], variant: PairedRetrievalQuery) -> list[SearchHit]:
    tagged: list[SearchHit] = []
    for hit in hits:
        metadata = dict(hit.metadata or {})
        features = query_intent_scoring_features(hit, variant)
        metadata.update(
            {
                "query_intent": variant.intent.value,
                "query_variant_id": variant.query_id,
                "query_variant": variant.query,
                "query_purpose": variant.purpose,
                "query_expansion_terms": list(variant.expansion_terms),
                "authority_score": features["authority_score"],
                "recency_score": features["recency_score"],
                "exactness_score": features["exactness_score"],
                "adverse_relevance_score": features["adverse_relevance_score"],
                "intent_score_multiplier": features["intent_score_multiplier"],
            }
        )
        tagged.append(
            SearchHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                title=hit.title,
                document_type=hit.document_type,
                source_id=hit.source_id,
                authority_level=hit.authority_level,
                citation=hit.citation,
                text=hit.text,
                score=hit.score * features["intent_score_multiplier"],
                retriever=f"{hit.retriever}:{variant.intent.value}",
                year=hit.year,
                page_start=hit.page_start,
                page_end=hit.page_end,
                source_url=hit.source_url,
                local_path=hit.local_path,
                metadata=metadata,
            )
        )
    return tagged


def query_intent_scoring_features(hit: SearchHit, variant: PairedRetrievalQuery) -> dict[str, float]:
    authority = authority_score(hit.authority_level)
    recency = recency_score(hit.year)
    exactness = exactness_score(hit=hit, query=variant.query)
    adverse = adverse_relevance_score(hit=hit, variant=variant)
    if variant.intent == RetrievalQueryIntent.SUPPORTIVE:
        signal_score = supportive_relevance_score(hit)
    else:
        signal_score = adverse
    multiplier = 0.85 + (0.25 * authority) + (0.15 * recency) + (0.25 * exactness) + (0.25 * signal_score)
    if variant.intent in {
        RetrievalQueryIntent.ADVERSE,
        RetrievalQueryIntent.LIMITATION,
        RetrievalQueryIntent.EXCEPTION,
        RetrievalQueryIntent.PROCEDURAL_RISK,
    }:
        multiplier += 0.08
    return {
        "authority_score": round(authority, 6),
        "recency_score": round(recency, 6),
        "exactness_score": round(exactness, 6),
        "adverse_relevance_score": round(adverse, 6),
        "intent_score_multiplier": round(multiplier, 6),
    }


def authority_score(authority_level: int) -> float:
    if authority_level <= 1:
        return 1.0
    if authority_level <= 3:
        return 0.9
    if authority_level <= 5:
        return 0.72
    if authority_level <= 7:
        return 0.55
    return 0.35


def recency_score(year: int | None, *, current_year: int | None = None) -> float:
    if year is None:
        return 0.5
    resolved_current_year = current_year or datetime.utcnow().year
    age = max(0, resolved_current_year - year)
    if age <= 5:
        return 1.0
    if age <= 20:
        return 0.85
    if age <= 50:
        return 0.68
    return 0.5


def exactness_score(*, hit: SearchHit, query: str) -> float:
    metadata = dict(hit.metadata or {})
    if metadata.get("exact_citation_match"):
        return 1.0
    query_terms = set(_terms(query))
    if not query_terms:
        return 0.0
    title_terms = set(_terms(hit.title))
    citation_terms = set(_terms(hit.citation))
    text_terms = set(_terms(hit.text[:1000]))
    title_overlap = len(query_terms.intersection(title_terms)) / len(query_terms)
    citation_overlap = len(query_terms.intersection(citation_terms)) / len(query_terms)
    text_overlap = len(query_terms.intersection(text_terms)) / len(query_terms)
    return min(1.0, (0.45 * title_overlap) + (0.45 * citation_overlap) + (0.10 * text_overlap))


def adverse_relevance_score(*, hit: SearchHit, variant: PairedRetrievalQuery) -> float:
    terms = set(_terms(" ".join([hit.title, hit.citation, hit.text[:2000]])))
    if not terms:
        return 0.0
    matched = terms.intersection(ADVERSE_SIGNAL_TERMS.union(set(_terms(" ".join(variant.expansion_terms)))))
    raw = len(matched) / 6
    if variant.intent in {
        RetrievalQueryIntent.ADVERSE,
        RetrievalQueryIntent.LIMITATION,
        RetrievalQueryIntent.EXCEPTION,
        RetrievalQueryIntent.PROCEDURAL_RISK,
    }:
        raw += 0.2
    return min(1.0, raw)


def supportive_relevance_score(hit: SearchHit) -> float:
    terms = set(_terms(" ".join([hit.title, hit.citation, hit.text[:2000]])))
    if not terms:
        return 0.0
    return min(1.0, len(terms.intersection(SUPPORTIVE_SIGNAL_TERMS)) / 5)


def query_intent_trace(variants: Iterable[PairedRetrievalQuery]) -> list[dict[str, object]]:
    return [
        {
            "stage": "query_expansion",
            "query_intent": variant.intent.value,
            "query_variant_id": variant.query_id,
            "query": variant.query,
            "purpose": variant.purpose,
            "expansion_terms": list(variant.expansion_terms),
        }
        for variant in variants
    ]


def _terms(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-zA-Z][a-zA-Z_]{2,}", text.lower())]


def _stable_slug(value: str) -> str:
    terms = _terms(value)
    return "-".join(terms[:10]) or "query"
