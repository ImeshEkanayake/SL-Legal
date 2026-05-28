from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import RetrievalFilters
from .retrieval import SearchHit


ACT_NUMBER_RE = re.compile(
    r"\b(?:act\s*,?\s*)?no\.?\s*([0-9]+[a-z]?)\s+of\s+(\d{4})\b",
    re.IGNORECASE,
)
PROVISION_INDICATOR_RE = re.compile(r"\b(section|sections|sec\.?|s\.|article|articles|art\.?)\s+", re.IGNORECASE)
PROVISION_LABEL_RE = re.compile(r"[0-9]+[a-z]?(?:\s*\(\s*[a-z0-9]+\s*\))*", re.IGNORECASE)
PROVISION_SEGMENT_STOP_RE = re.compile(
    r"\b(of|under|from|in|by|for|regarding|concerning|where|which|that|shall|is|are)\b|[.;:\n]",
    re.IGNORECASE,
)
CASE_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9 .&'’/-]{1,80}?)\s+(?:v\.?|vs\.?|versus)\s+([A-Z][A-Za-z0-9 .&'’/-]{1,80}?)(?=$|[,.;:\n])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActCitationSignal:
    number: str
    year: int


@dataclass(frozen=True)
class ProvisionSignal:
    kind: str
    label: str
    normalized_label: str


@dataclass(frozen=True)
class CaseNameSignal:
    left_party: str
    right_party: str
    normalized_name: str


@dataclass(frozen=True)
class ExactCitationSignals:
    act_citations: tuple[ActCitationSignal, ...]
    provisions: tuple[ProvisionSignal, ...]
    case_names: tuple[CaseNameSignal, ...] = ()

    @property
    def has_signals(self) -> bool:
        return bool(self.act_citations or self.provisions or self.case_names)


def normalize_act_number(number: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", number).upper()


def normalize_provision_label(label: str) -> str:
    compact = re.sub(r"\s+", "", label)
    compact = re.sub(r"\(\s*([a-z0-9]+)\s*\)", lambda match: f"({match.group(1).lower()})", compact, flags=re.IGNORECASE)
    return compact.lower()


def normalize_case_party(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip(" ,.;:\n\t")).strip()
    cleaned = re.sub(r"^(find|search for|locate|case of|judgment in)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def normalize_case_name(left_party: str, right_party: str) -> str:
    return f"{normalize_case_party(left_party)} v {normalize_case_party(right_party)}"


def parse_exact_citation_signals(query: str) -> ExactCitationSignals:
    act_signals: list[ActCitationSignal] = []
    seen_acts: set[tuple[str, int]] = set()
    for match in ACT_NUMBER_RE.finditer(query):
        number = normalize_act_number(match.group(1))
        year = int(match.group(2))
        key = (number, year)
        if key not in seen_acts:
            seen_acts.add(key)
            act_signals.append(ActCitationSignal(number=number, year=year))

    provision_signals: list[ProvisionSignal] = []
    seen_provisions: set[tuple[str, str]] = set()
    for match in PROVISION_INDICATOR_RE.finditer(query):
        kind = match.group(1).rstrip(".").lower()
        segment = query[match.end() : match.end() + 120]
        stop_match = PROVISION_SEGMENT_STOP_RE.search(segment)
        if stop_match and stop_match.start() > 0:
            segment = segment[: stop_match.start()]
        for label_match in PROVISION_LABEL_RE.finditer(segment):
            label = label_match.group(0)
            normalized = normalize_provision_label(label)
            key = (kind, normalized)
            if key not in seen_provisions:
                seen_provisions.add(key)
                provision_signals.append(ProvisionSignal(kind=kind, label=label, normalized_label=normalized))

    case_name_signals: list[CaseNameSignal] = []
    seen_case_names: set[str] = set()
    for match in CASE_NAME_RE.finditer(query):
        left_party = normalize_case_party(match.group(1))
        right_party = normalize_case_party(match.group(2))
        normalized_name = normalize_case_name(left_party, right_party)
        normalized_key = normalized_name.lower()
        if left_party and right_party and normalized_key not in seen_case_names:
            seen_case_names.add(normalized_key)
            case_name_signals.append(
                CaseNameSignal(
                    left_party=left_party,
                    right_party=right_party,
                    normalized_name=normalized_name,
                )
            )

    return ExactCitationSignals(
        act_citations=tuple(act_signals),
        provisions=tuple(provision_signals),
        case_names=tuple(case_name_signals),
    )


def provision_label_to_postgres_regex(label: str) -> str:
    normalized = normalize_provision_label(label)
    tokens = re.findall(r"[0-9]+[a-z]?|\([a-z0-9]+\)", normalized)
    if not tokens:
        return re.escape(normalized)
    parts: list[str] = []
    for token in tokens:
        if token.startswith("("):
            inner = re.escape(token[1:-1])
            parts.append(r"\(\s*" + inner + r"\s*\)")
            continue
        number_match = re.fullmatch(r"([0-9]+)([a-z]?)", token)
        if number_match:
            number, suffix = number_match.groups()
            part = re.escape(number)
            if suffix:
                part += r"\s*" + re.escape(suffix)
            parts.append(part)
            continue
        parts.append(re.escape(token))
    return r"(^|[^[:alnum:]])" + r"\s*".join(parts) + r"([^[:alnum:]]|$)"


def provision_signal_to_postgres_regex(provision: ProvisionSignal, *, require_kind_prefix: bool) -> str:
    label_regex = provision_label_to_postgres_regex(provision.normalized_label)
    if not require_kind_prefix:
        return label_regex
    kind = provision.kind.lower()
    if kind in {"article", "articles", "art"}:
        prefix = r"(^|[^[:alnum:]])(article|articles|art\.?)\s*"
    else:
        prefix = r"(^|[^[:alnum:]])(section|sections|sec\.?|s\.?)\s*"
    return prefix + label_regex.removeprefix(r"(^|[^[:alnum:]])")


def exact_filter_sql(filters: RetrievalFilters) -> tuple[list[str], dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters.document_types:
        clauses.append("rc.document_type = ANY(:document_types)")
        params["document_types"] = filters.document_types
    if filters.source_ids:
        clauses.append("rc.source_id = ANY(:source_ids)")
        params["source_ids"] = filters.source_ids
    if filters.authority_levels:
        clauses.append("rc.authority_level = ANY(:authority_levels)")
        params["authority_levels"] = filters.authority_levels
    if filters.years:
        clauses.append("rc.year = ANY(:years)")
        params["years"] = filters.years
    if filters.year_from is not None:
        clauses.append("rc.year >= :year_from")
        params["year_from"] = filters.year_from
    if filters.year_to is not None:
        clauses.append("rc.year <= :year_to")
        params["year_to"] = filters.year_to
    if filters.language:
        clauses.append("rc.language = :language")
        params["language"] = filters.language
    if filters.require_official:
        clauses.append("rc.authority_level <= 4")
    return clauses, params


def build_exact_sql(signals: ExactCitationSignals, filters: RetrievalFilters) -> tuple[str, dict[str, Any]]:
    clauses, params = exact_filter_sql(filters)
    match_groups: list[str] = []

    if signals.act_citations:
        act_clauses: list[str] = []
        for index, citation in enumerate(signals.act_citations):
            number_key = f"act_number_{index}"
            year_key = f"act_year_{index}"
            params[number_key] = citation.number
            params[year_key] = citation.year
            act_clauses.append(
                "("
                "upper(regexp_replace(coalesce(d.number, ''), '[^0-9A-Za-z]', '', 'g')) = "
                f":{number_key} AND d.year = :{year_key}"
                ")"
            )
        match_groups.append("(" + " OR ".join(act_clauses) + ")")

    if signals.provisions:
        provision_clauses: list[str] = []
        for index, provision in enumerate(signals.provisions):
            regex_key = f"provision_regex_{index}"
            params[regex_key] = provision_signal_to_postgres_regex(
                provision,
                require_kind_prefix=not signals.act_citations,
            )
            provision_clauses.append(f"rc.chunk_text ~* :{regex_key}")
        provision_group = "(" + " OR ".join(provision_clauses) + ")"
        if signals.act_citations:
            match_groups.append(provision_group)
        else:
            match_groups = [provision_group]

    if signals.case_names:
        case_clauses: list[str] = []
        for index, case_name in enumerate(signals.case_names):
            left_key = f"case_left_{index}"
            right_key = f"case_right_{index}"
            full_key = f"case_full_{index}"
            params[left_key] = f"%{case_name.left_party}%"
            params[right_key] = f"%{case_name.right_party}%"
            params[full_key] = f"%{case_name.normalized_name.replace(' v ', '%')}%"
            case_clauses.append(
                f"((rc.title ILIKE :{left_key} AND rc.title ILIKE :{right_key})"
                f" OR (rc.citation ILIKE :{left_key} AND rc.citation ILIKE :{right_key})"
                f" OR rc.title ILIKE :{full_key}"
                f" OR rc.citation ILIKE :{full_key})"
            )
        match_groups.append("(" + " OR ".join(case_clauses) + ")")

    if match_groups:
        clauses.append(" AND ".join(match_groups))

    where_sql = " AND ".join(clauses) if clauses else "TRUE"
    params["limit"] = 50

    sql = f"""
        SELECT
            rc.chunk_id,
            rc.document_id,
            rc.source_id,
            rc.document_type,
            rc.title,
            rc.year,
            rc.authority_level,
            rc.page_start,
            rc.page_end,
            rc.chunk_text,
            rc.citation,
            rc.source_url,
            rc.local_path,
            rc.quality_flags,
            rc.metadata,
            rc.text_version_id,
            rc.text_origin,
            rc.source_language,
            rc.translated_from_language,
            rc.translation_review_status
        FROM retrieval_chunks rc
        JOIN documents d ON d.document_id = rc.document_id
        WHERE {where_sql}
        ORDER BY rc.authority_level ASC, rc.year DESC NULLS LAST, rc.page_start ASC NULLS LAST, rc.chunk_index ASC
        LIMIT :limit
    """
    return sql, params


def row_to_search_hit(row: dict[str, Any], *, rank: int, signals: ExactCitationSignals) -> SearchHit:
    quality_flags = list(row.get("quality_flags") or [])
    metadata = dict(row.get("metadata") or {})
    metadata["quality_flags"] = quality_flags
    for key in (
        "text_version_id",
        "text_origin",
        "source_language",
        "translated_from_language",
        "translation_review_status",
    ):
        if row.get(key) is not None and key not in metadata:
            metadata[key] = row.get(key)
    metadata["exact_citation_match"] = True
    metadata["matched_act_citations"] = [f"No. {signal.number} of {signal.year}" for signal in signals.act_citations]
    metadata["matched_provisions"] = [signal.normalized_label for signal in signals.provisions]
    metadata["matched_case_names"] = [signal.normalized_name for signal in signals.case_names]
    return SearchHit(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        title=str(row["title"]),
        document_type=str(row["document_type"]),
        source_id=str(row["source_id"]),
        authority_level=int(row["authority_level"]),
        citation=str(row["citation"]),
        text=str(row["chunk_text"]),
        score=1000.0 - rank,
        retriever="exact_citation_provision",
        year=int(row["year"]) if row.get("year") is not None else None,
        page_start=int(row["page_start"]) if row.get("page_start") is not None else None,
        page_end=int(row["page_end"]) if row.get("page_end") is not None else None,
        source_url=str(row["source_url"]) if row.get("source_url") else None,
        local_path=str(row["local_path"]) if row.get("local_path") else None,
        metadata=metadata,
    )


def resolve_exact_citation_hits(
    *,
    query: str,
    filters: RetrievalFilters,
    session: Session,
) -> list[SearchHit]:
    signals = parse_exact_citation_signals(query)
    if not signals.has_signals:
        return []
    sql, params = build_exact_sql(signals, filters)
    rows = session.execute(text(sql), params).mappings().all()
    return [row_to_search_hit(dict(row), rank=rank, signals=signals) for rank, row in enumerate(rows, start=1)]
