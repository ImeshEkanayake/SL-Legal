from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable


DEFAULT_SUMMARY_TYPE = "extractive_10pct"

LEGAL_TITLE_HINTS = (
    "Industrial Disputes",
    "Collective Agreement",
    "Constitution",
    "Fundamental Rights",
    "Land Acquisition",
    "Inland Revenue",
    "Municipal Council",
    "Municipal Councils",
    "Urban Council",
    "Urban Councils",
    "Pradeshiya Sabha",
    "Pradeshiya Sabhas",
    "Companies",
    "Companies Act",
    "Penal Code",
    "Evidence Ordinance",
    "Criminal Procedure Code",
    "Customs",
    "Customs Ordinance",
    "Revenue Protection",
    "Immigrants and Emigrants",
    "Intellectual Property",
    "Rent Restriction",
    "Motor Traffic",
    "Bribery",
    "Anti-Corruption",
    "Personal Data Protection",
    "Computer Crimes",
    "Prevention of Domestic Violence",
    "Banking",
    "Microfinance",
    "National Environmental",
    "Urban Development Authority",
    "Parliamentary Elections",
    "Presidential Elections",
    "Shop and Office",
    "Wages Boards",
    "Termination of Employment",
    "Apartment Ownership",
    "Consumer Affairs",
    "Bail",
    "Judicature",
)
GENERIC_TITLE_HINTS = {"Constitution", "Fundamental Rights"}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")
STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "under",
    "about",
    "after",
    "before",
    "between",
    "where",
    "which",
    "says",
    "wants",
    "case",
    "legal",
    "sri",
    "lanka",
    "ceylon",
    "act",
    "acts",
    "law",
    "laws",
    "section",
    "article",
    "ordinance",
}


@dataclass(frozen=True)
class TwoStageRetrievalRequest:
    query: str
    document_types: tuple[str, ...] = ()
    language: str | None = "English"


@dataclass(frozen=True)
class TwoStageRetrievalConfig:
    summary_type: str = DEFAULT_SUMMARY_TYPE
    stage1_limit: int = 750
    title_expansion_limit: int = 1500
    chunks_per_document: int = 3

    def validate(self) -> None:
        if self.stage1_limit < 1:
            raise ValueError("stage1_limit must be >= 1")
        if self.title_expansion_limit < 0:
            raise ValueError("title_expansion_limit must be >= 0")
        if self.chunks_per_document < 0:
            raise ValueError("chunks_per_document must be >= 0")


@dataclass
class SummaryCandidate:
    document_id: str
    text_version_id: str
    title: str
    document_type: str
    source_id: str
    year: int | None
    language: str | None
    source_url: str | None
    local_path: str | None
    summary_text: str
    summary_rank: float
    title_rank: float
    title_similarity: float
    stage1_score: float
    stage1_rank: int = 0


@dataclass
class EvidenceChunk:
    chunk_id: str
    page_start: int | None
    page_end: int | None
    chunk_text: str
    chunk_rank: float
    chunk_similarity: float
    chunk_score: float


@dataclass
class FullTextMetrics:
    text_version_id: str
    char_count: int
    token_estimate: int
    text_origin: str
    source_language: str | None
    translated_from_language: str | None
    translation_review_status: str | None
    quality_flags: list[str]
    full_text_rank: float
    title_rank: float
    title_similarity: float
    term_hits: int
    phrase_hits: int


@dataclass
class RankedDocument:
    candidate: SummaryCandidate
    metrics: FullTextMetrics
    evidence_chunks: list[EvidenceChunk]
    term_coverage: float
    raw_score: float
    relevance_score: float
    final_rank: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class TwoStageRetrievalResult:
    request: TwoStageRetrievalRequest
    config: TwoStageRetrievalConfig
    candidates: list[SummaryCandidate]
    ranked_documents: list[RankedDocument]
    elapsed_ms: int
    tokens: list[str]
    title_hints: list[str]


def normalize_retrieval_request(request: TwoStageRetrievalRequest) -> TwoStageRetrievalRequest:
    query = re.sub(r"\s+", " ", request.query).strip()
    if not query:
        raise ValueError("query must not be empty")
    document_types = tuple(dict.fromkeys(item.strip() for item in request.document_types if item.strip()))
    language = request.language.strip() if isinstance(request.language, str) and request.language.strip() else None
    return TwoStageRetrievalRequest(query=query, document_types=document_types, language=language)


def tokenize(text: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in WORD_RE.finditer(text.lower()):
        token = match.group(0)
        if token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def to_prefix_tsquery(tokens: Iterable[str], *, max_terms: int = 24) -> str:
    safe_terms = []
    for token in list(tokens)[:max_terms]:
        clean = re.sub(r"[^a-z0-9]", "", token.lower())
        if len(clean) >= 3:
            safe_terms.append(f"{clean}:*")
    if not safe_terms:
        return "document:*"
    return " | ".join(safe_terms)


def important_phrases(text: str) -> list[str]:
    phrases = []
    quoted = re.findall(r'"([^"]{4,80})"', text)
    phrases.extend(quoted)
    titleish = re.findall(r"\b(?:[A-Z][A-Za-z]+(?:\s+|$)){2,6}", text)
    phrases.extend(item.strip() for item in titleish)
    normalized = []
    seen = set()
    for phrase in phrases:
        cleaned = re.sub(r"\s+", " ", phrase.strip().lower())
        if len(cleaned) >= 5 and cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return normalized[:16]


def legal_title_hints(query: str) -> list[str]:
    lower = query.lower()
    return [hint for hint in LEGAL_TITLE_HINTS if hint.lower() in lower]


def title_hint_multiplier(query: str, title: str) -> float:
    hints = [hint for hint in legal_title_hints(query) if hint not in GENERIC_TITLE_HINTS]
    if not hints:
        return 1.0
    lower_title = title.lower()
    if any(hint.lower() in lower_title for hint in hints):
        return 1.18
    return 0.62


def excerpt_around_terms(text: str, tokens: list[str], *, radius: int = 420) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return ""
    lower = collapsed.lower()
    positions = [lower.find(token) for token in tokens if lower.find(token) >= 0]
    if not positions:
        return collapsed[: radius * 2].strip()
    center = min(positions)
    start = max(0, center - radius)
    end = min(len(collapsed), center + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(collapsed) else ""
    return f"{prefix}{collapsed[start:end].strip()}{suffix}"


def sql_filter_clause(request: TwoStageRetrievalRequest, *, summary_type: str) -> tuple[str, dict[str, Any]]:
    clauses = [
        "ds.summary_type = %(summary_type)s",
        "d.acquisition_status = 'downloaded'",
        "dtv.full_text IS NOT NULL",
        "dtv.char_count > 0",
    ]
    params: dict[str, Any] = {"summary_type": summary_type}
    if request.language:
        clauses.append("(d.language = %(language)s OR ds.language = %(language)s OR dtv.language = %(language)s)")
        params["language"] = request.language
    if request.document_types:
        clauses.append("d.document_type = ANY(%(document_types)s)")
        params["document_types"] = list(request.document_types)
    return " AND ".join(clauses), params


def search_summary_candidates(
    conn: Any,
    request: TwoStageRetrievalRequest,
    config: TwoStageRetrievalConfig,
) -> list[SummaryCandidate]:
    request = normalize_retrieval_request(request)
    config.validate()
    tokens = tokenize(request.query)
    tsquery = to_prefix_tsquery(tokens)
    filters, filter_params = sql_filter_clause(request, summary_type=config.summary_type)
    params = filter_params | {
        "tsquery": tsquery,
        "query": request.query,
        "limit": config.stage1_limit,
    }
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            WITH matches AS (
                SELECT
                    d.document_id,
                    ds.text_version_id,
                    d.title,
                    d.document_type,
                    d.source_id,
                    d.year,
                    d.language,
                    d.source_url,
                    d.local_path,
                    ds.summary_text,
                    ts_rank_cd(to_tsvector('simple', ds.summary_text), to_tsquery('simple', %(tsquery)s), 32) AS summary_rank,
                    ts_rank_cd(to_tsvector('simple', d.title), to_tsquery('simple', %(tsquery)s), 32) AS title_rank,
                    similarity(lower(d.title), lower(%(query)s)) AS title_similarity
                FROM document_summaries ds
                JOIN documents d ON d.document_id = ds.document_id
                JOIN document_text_versions dtv ON dtv.text_version_id = ds.text_version_id
                WHERE {filters}
                  AND (
                        to_tsvector('simple', ds.summary_text) @@ to_tsquery('simple', %(tsquery)s)
                        OR to_tsvector('simple', d.title) @@ to_tsquery('simple', %(tsquery)s)
                        OR similarity(lower(d.title), lower(%(query)s)) >= 0.08
                  )
            )
            SELECT
                document_id,
                text_version_id,
                title,
                document_type,
                source_id,
                year,
                language,
                source_url,
                local_path,
                summary_text,
                summary_rank,
                title_rank,
                title_similarity,
                (
                    summary_rank
                    + (3.0 * title_rank)
                    + (1.5 * title_similarity)
                    + CASE
                        WHEN document_type IN ('Constitution', 'Core Legislation', 'Act') THEN 0.35
                        WHEN document_type LIKE '%%Judgment%%' THEN 0.25
                        WHEN document_type LIKE '%%Gazette%%' THEN 0.15
                        ELSE 0.0
                      END
                ) AS stage1_score
            FROM matches
            ORDER BY stage1_score DESC, summary_rank DESC, title_rank DESC, year DESC NULLS LAST, title
            LIMIT %(limit)s
            """,
            params,
        )
        rows = cursor.fetchall()
    candidates_by_doc: dict[str, SummaryCandidate] = {}
    for row in rows:
        candidate = SummaryCandidate(
            document_id=str(row[0]),
            text_version_id=str(row[1]),
            title=str(row[2]),
            document_type=str(row[3]),
            source_id=str(row[4]),
            year=row[5],
            language=row[6],
            source_url=row[7],
            local_path=row[8],
            summary_text=str(row[9] or ""),
            summary_rank=float(row[10] or 0.0),
            title_rank=float(row[11] or 0.0),
            title_similarity=float(row[12] or 0.0),
            stage1_score=float(row[13] or 0.0),
        )
        previous = candidates_by_doc.get(candidate.document_id)
        if previous is None or candidate.stage1_score > previous.stage1_score:
            candidates_by_doc[candidate.document_id] = candidate
    hints = legal_title_hints(request.query)
    if hints and config.title_expansion_limit:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    d.document_id,
                    ds.text_version_id,
                    d.title,
                    d.document_type,
                    d.source_id,
                    d.year,
                    d.language,
                    d.source_url,
                    d.local_path,
                    ds.summary_text,
                    ts_rank_cd(to_tsvector('simple', ds.summary_text), to_tsquery('simple', %(tsquery)s), 32) AS summary_rank,
                    ts_rank_cd(to_tsvector('simple', d.title), to_tsquery('simple', %(tsquery)s), 32) AS title_rank,
                    similarity(lower(d.title), lower(%(query)s)) AS title_similarity,
                    (
                        0.6
                        + ts_rank_cd(to_tsvector('simple', ds.summary_text), to_tsquery('simple', %(tsquery)s), 32)
                        + (3.5 * ts_rank_cd(to_tsvector('simple', d.title), to_tsquery('simple', %(tsquery)s), 32))
                        + (2.0 * similarity(lower(d.title), lower(%(query)s)))
                    ) AS stage1_score
                FROM document_summaries ds
                JOIN documents d ON d.document_id = ds.document_id
                JOIN document_text_versions dtv ON dtv.text_version_id = ds.text_version_id
                WHERE {filters}
                  AND EXISTS (
                    SELECT 1
                    FROM unnest(%(title_hints)s::text[]) hint
                    WHERE d.title ILIKE ('%%' || hint || '%%')
                  )
                ORDER BY stage1_score DESC, d.year DESC NULLS LAST, d.title
                LIMIT %(title_expansion_limit)s
                """,
                params | {"title_hints": hints, "title_expansion_limit": config.title_expansion_limit},
            )
            expansion_rows = cursor.fetchall()
        for row in expansion_rows:
            candidate = SummaryCandidate(
                document_id=str(row[0]),
                text_version_id=str(row[1]),
                title=str(row[2]),
                document_type=str(row[3]),
                source_id=str(row[4]),
                year=row[5],
                language=row[6],
                source_url=row[7],
                local_path=row[8],
                summary_text=str(row[9] or ""),
                summary_rank=float(row[10] or 0.0),
                title_rank=float(row[11] or 0.0),
                title_similarity=float(row[12] or 0.0),
                stage1_score=float(row[13] or 0.0),
            )
            previous = candidates_by_doc.get(candidate.document_id)
            if previous is None or candidate.stage1_score > previous.stage1_score:
                candidates_by_doc[candidate.document_id] = candidate
    candidates = sorted(
        candidates_by_doc.values(),
        key=lambda item: (item.stage1_score, item.summary_rank, item.title_rank, item.year or 0),
        reverse=True,
    )
    for rank, candidate in enumerate(candidates, start=1):
        candidate.stage1_rank = rank
    return candidates


def load_full_text_metrics(
    conn: Any,
    candidates: list[SummaryCandidate],
    request: TwoStageRetrievalRequest,
) -> dict[str, FullTextMetrics]:
    request = normalize_retrieval_request(request)
    if not candidates:
        return {}
    tokens = tokenize(request.query)
    phrases = important_phrases(request.query)
    tsquery = to_prefix_tsquery(tokens)
    candidate_versions = [(candidate.document_id, candidate.text_version_id) for candidate in candidates]
    with conn.cursor() as cursor:
        cursor.execute(
            """
            WITH target(document_id, text_version_id) AS (
                SELECT * FROM unnest(%(document_ids)s::text[], %(text_version_ids)s::text[])
            )
            SELECT
                d.document_id,
                dtv.text_version_id,
                dtv.char_count,
                dtv.token_estimate,
                dtv.text_origin,
                dtv.source_language,
                dtv.translated_from_language,
                dtv.translation_review_status,
                dtv.quality_flags,
                ts_rank_cd(to_tsvector('simple', left(dtv.full_text, 800000)), to_tsquery('simple', %(tsquery)s), 32) AS full_text_rank,
                ts_rank_cd(to_tsvector('simple', d.title), to_tsquery('simple', %(tsquery)s), 32) AS title_rank,
                similarity(lower(d.title), lower(%(query)s)) AS title_similarity,
                (
                    SELECT count(*)
                    FROM unnest(%(tokens)s::text[]) token
                    WHERE position(token in lower(dtv.full_text)) > 0
                ) AS term_hits,
                (
                    SELECT count(*)
                    FROM unnest(%(phrases)s::text[]) phrase
                    WHERE position(phrase in lower(dtv.full_text)) > 0
                ) AS phrase_hits
            FROM target
            JOIN documents d ON d.document_id = target.document_id
            JOIN document_text_versions dtv ON dtv.text_version_id = target.text_version_id
            """,
            {
                "document_ids": [item[0] for item in candidate_versions],
                "text_version_ids": [item[1] for item in candidate_versions],
                "tsquery": tsquery,
                "query": request.query,
                "tokens": tokens,
                "phrases": phrases,
            },
        )
        rows = cursor.fetchall()
    metrics: dict[str, FullTextMetrics] = {}
    for row in rows:
        metrics[str(row[0])] = FullTextMetrics(
            text_version_id=str(row[1]),
            char_count=int(row[2] or 0),
            token_estimate=int(row[3] or 0),
            text_origin=str(row[4] or "source"),
            source_language=row[5],
            translated_from_language=row[6],
            translation_review_status=row[7],
            quality_flags=list(row[8] or []),
            full_text_rank=float(row[9] or 0.0),
            title_rank=float(row[10] or 0.0),
            title_similarity=float(row[11] or 0.0),
            term_hits=int(row[12] or 0),
            phrase_hits=int(row[13] or 0),
        )
    return metrics


def load_best_evidence_chunks(
    conn: Any,
    candidates: list[SummaryCandidate],
    request: TwoStageRetrievalRequest,
    *,
    chunks_per_document: int,
) -> dict[str, list[EvidenceChunk]]:
    request = normalize_retrieval_request(request)
    if not candidates or chunks_per_document <= 0:
        return {}
    tokens = tokenize(request.query)
    tsquery = to_prefix_tsquery(tokens)
    document_ids = [candidate.document_id for candidate in candidates]
    with conn.cursor() as cursor:
        cursor.execute(
            """
            WITH target(document_id) AS (
                SELECT unnest(%(document_ids)s::text[])
            ),
            ranked AS (
                SELECT
                    rc.document_id,
                    rc.chunk_id,
                    rc.page_start,
                    rc.page_end,
                    rc.chunk_text,
                    ts_rank_cd(to_tsvector('simple', rc.chunk_text), to_tsquery('simple', %(tsquery)s), 32) AS chunk_rank,
                    similarity(lower(left(rc.chunk_text, 5000)), lower(%(query)s)) AS chunk_similarity,
                    row_number() OVER (
                        PARTITION BY rc.document_id
                        ORDER BY
                            ts_rank_cd(to_tsvector('simple', rc.chunk_text), to_tsquery('simple', %(tsquery)s), 32) DESC,
                            similarity(lower(left(rc.chunk_text, 5000)), lower(%(query)s)) DESC,
                            rc.page_start NULLS LAST,
                            rc.chunk_index
                    ) AS rn
                FROM retrieval_chunks rc
                JOIN target ON target.document_id = rc.document_id
                WHERE (
                    to_tsvector('simple', rc.chunk_text) @@ to_tsquery('simple', %(tsquery)s)
                    OR similarity(lower(left(rc.chunk_text, 5000)), lower(%(query)s)) >= 0.03
                )
            )
            SELECT
                document_id,
                chunk_id,
                page_start,
                page_end,
                chunk_text,
                chunk_rank,
                chunk_similarity,
                (chunk_rank + chunk_similarity) AS chunk_score
            FROM ranked
            WHERE rn <= %(chunks_per_document)s
            ORDER BY document_id, rn
            """,
            {
                "document_ids": document_ids,
                "tsquery": tsquery,
                "query": request.query,
                "chunks_per_document": chunks_per_document,
            },
        )
        rows = cursor.fetchall()
    by_document: dict[str, list[EvidenceChunk]] = {}
    for row in rows:
        by_document.setdefault(str(row[0]), []).append(
            EvidenceChunk(
                chunk_id=str(row[1]),
                page_start=row[2],
                page_end=row[3],
                chunk_text=str(row[4] or ""),
                chunk_rank=float(row[5] or 0.0),
                chunk_similarity=float(row[6] or 0.0),
                chunk_score=float(row[7] or 0.0),
            )
        )
    return by_document


def source_quality_multiplier(candidate: SummaryCandidate, metrics: FullTextMetrics) -> float:
    multiplier = 1.0
    if candidate.document_type in {"Constitution", "Core Legislation", "Act"}:
        multiplier *= 1.15
    elif "Judgment" in candidate.document_type:
        multiplier *= 1.12
    elif "Gazette" in candidate.document_type:
        multiplier *= 1.04
    elif "Parliament Paper" in candidate.document_type:
        multiplier *= 0.86
    if metrics.text_origin == "translated":
        multiplier *= 0.82
    if metrics.translation_review_status and metrics.translation_review_status not in {"not_applicable", "reviewed"}:
        multiplier *= 0.86
    flags = set(metrics.quality_flags)
    if {"low_confidence_ocr", "low_ocr_confidence"}.intersection(flags):
        multiplier *= 0.75
    if "machine_translation_unreviewed" in flags:
        multiplier *= 0.80
    return multiplier


def safe_ratio(value: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, value / maximum))


def rank_stage2_documents(
    candidates: list[SummaryCandidate],
    metrics_by_document: dict[str, FullTextMetrics],
    chunks_by_document: dict[str, list[EvidenceChunk]],
    request: TwoStageRetrievalRequest,
) -> list[RankedDocument]:
    request = normalize_retrieval_request(request)
    tokens = tokenize(request.query)
    phrases = important_phrases(request.query)
    max_stage1 = max((candidate.stage1_score for candidate in candidates), default=0.0)
    max_full_text = max((metrics.full_text_rank for metrics in metrics_by_document.values()), default=0.0)
    max_title = max((metrics.title_rank + metrics.title_similarity for metrics in metrics_by_document.values()), default=0.0)
    max_chunk = max(
        (chunk.chunk_score for chunks in chunks_by_document.values() for chunk in chunks),
        default=0.0,
    )
    ranked: list[RankedDocument] = []
    for candidate in candidates:
        metrics = metrics_by_document.get(candidate.document_id)
        if metrics is None:
            continue
        chunks = chunks_by_document.get(candidate.document_id, [])
        best_chunk_score = max((chunk.chunk_score for chunk in chunks), default=0.0)
        term_coverage = metrics.term_hits / max(1, len(tokens))
        title_score = metrics.title_rank + metrics.title_similarity
        phrase_score = 0.0 if not phrases else min(1.0, metrics.phrase_hits / len(phrases))
        raw = (
            0.22 * safe_ratio(candidate.stage1_score, max_stage1)
            + 0.34 * safe_ratio(metrics.full_text_rank, max_full_text)
            + 0.20 * safe_ratio(best_chunk_score, max_chunk)
            + 0.15 * term_coverage
            + 0.07 * safe_ratio(title_score, max_title)
            + 0.02 * phrase_score
        )
        raw *= source_quality_multiplier(candidate, metrics) * title_hint_multiplier(request.query, candidate.title)
        ranked.append(
            RankedDocument(
                candidate=candidate,
                metrics=metrics,
                evidence_chunks=chunks,
                term_coverage=term_coverage,
                raw_score=raw,
                relevance_score=0.0,
            )
        )
    ranked.sort(key=lambda item: item.raw_score, reverse=True)
    max_raw = max((item.raw_score for item in ranked), default=0.0)
    for rank, item in enumerate(ranked, start=1):
        item.final_rank = rank
        item.relevance_score = round(100.0 * safe_ratio(item.raw_score, max_raw), 2) if max_raw else 0.0
        if item.raw_score > 0 and item.relevance_score < 1.0:
            item.relevance_score = 1.0
    return ranked


def run_two_stage_retrieval(
    conn: Any,
    request: TwoStageRetrievalRequest,
    config: TwoStageRetrievalConfig | None = None,
) -> TwoStageRetrievalResult:
    request = normalize_retrieval_request(request)
    config = config or TwoStageRetrievalConfig()
    config.validate()
    started = time.perf_counter()
    candidates = search_summary_candidates(conn, request, config)
    metrics_by_document = load_full_text_metrics(conn, candidates, request)
    chunks_by_document = load_best_evidence_chunks(
        conn,
        candidates,
        request,
        chunks_per_document=config.chunks_per_document,
    )
    ranked = rank_stage2_documents(candidates, metrics_by_document, chunks_by_document, request)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return TwoStageRetrievalResult(
        request=request,
        config=config,
        candidates=candidates,
        ranked_documents=ranked,
        elapsed_ms=elapsed_ms,
        tokens=tokenize(request.query),
        title_hints=legal_title_hints(request.query),
    )


def serialize_ranked_document(item: RankedDocument, *, query: str, tokens: list[str]) -> dict[str, Any]:
    candidate = item.candidate
    metrics = item.metrics
    best_chunk = item.evidence_chunks[0] if item.evidence_chunks else None
    evidence_chunks = [
        {
            "chunk_id": chunk.chunk_id,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "chunk_score": round(chunk.chunk_score, 6),
            "chunk_text": chunk.chunk_text,
            "excerpt": excerpt_around_terms(chunk.chunk_text, tokens),
        }
        for chunk in item.evidence_chunks
    ]
    return {
        "rank": item.final_rank,
        "relevance_score": item.relevance_score,
        "document_id": candidate.document_id,
        "title": candidate.title,
        "document_type": candidate.document_type,
        "source_id": candidate.source_id,
        "year": candidate.year,
        "language": candidate.language,
        "text_version_id": candidate.text_version_id,
        "char_count": metrics.char_count,
        "text_origin": metrics.text_origin,
        "translation_review_status": metrics.translation_review_status,
        "quality_flags": metrics.quality_flags,
        "source_url": candidate.source_url,
        "local_path": candidate.local_path,
        "summary_search_excerpt": excerpt_around_terms(candidate.summary_text, tokens),
        "evidence_chunks": evidence_chunks,
        "best_full_text_chunk": {
            "chunk_id": best_chunk.chunk_id,
            "page_start": best_chunk.page_start,
            "page_end": best_chunk.page_end,
            "chunk_score": round(best_chunk.chunk_score, 6),
            "chunk_text": best_chunk.chunk_text,
            "excerpt": excerpt_around_terms(best_chunk.chunk_text, tokens),
        }
        if best_chunk
        else None,
        "scoring_breakdown": {
            "raw_score": round(item.raw_score, 8),
            "stage1_rank": candidate.stage1_rank,
            "stage1_score": round(candidate.stage1_score, 8),
            "summary_rank": round(candidate.summary_rank, 8),
            "title_rank": round(candidate.title_rank, 8),
            "title_similarity": round(candidate.title_similarity, 8),
            "full_text_rank": round(metrics.full_text_rank, 8),
            "term_hits": metrics.term_hits,
            "term_coverage": round(item.term_coverage, 6),
            "phrase_hits": metrics.phrase_hits,
            "evidence_chunk_count": len(item.evidence_chunks),
            "best_chunk_score": round(max((chunk.chunk_score for chunk in item.evidence_chunks), default=0.0), 8),
            "source_quality_multiplier": round(source_quality_multiplier(candidate, metrics), 6),
            "title_hint_multiplier": round(title_hint_multiplier(query, candidate.title), 6),
        },
    }
