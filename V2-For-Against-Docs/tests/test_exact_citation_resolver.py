from __future__ import annotations

from sl_legal_rag.exact_citation import (
    build_exact_sql,
    normalize_case_name,
    normalize_provision_label,
    parse_exact_citation_signals,
    provision_label_to_postgres_regex,
    row_to_search_hit,
)
from sl_legal_rag.models import RetrievalFilters


def test_parse_exact_act_and_multiple_provisions():
    signals = parse_exact_citation_signals(
        "Industrial Disputes (Amendment) Act No. 56 of 1999 sections 32A and 40(1)(ss)"
    )

    assert [(item.number, item.year) for item in signals.act_citations] == [("56", 1999)]
    assert [item.normalized_label for item in signals.provisions] == ["32a", "40(1)(ss)"]


def test_parse_case_name_signal_for_exact_case_retrieval():
    signals = parse_exact_citation_signals("Find Perera v Silva, about tenancy.")

    assert [item.normalized_name for item in signals.case_names] == ["Perera v Silva"]
    assert normalize_case_name(" Perera ", " Silva ") == "Perera v Silva"


def test_normalize_provision_label_compacts_spacing_and_case():
    assert normalize_provision_label("40 ( 1 ) (SS)") == "40(1)(ss)"


def test_provision_regex_allows_ocr_spacing():
    regex = provision_label_to_postgres_regex("40(1)(ss)")

    assert "40" in regex
    assert r"\s*" in regex
    assert "ss" in regex


def test_row_to_search_hit_marks_exact_match_metadata():
    signals = parse_exact_citation_signals("Act No. 56 of 1999 section 32A")
    hit = row_to_search_hit(
        {
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "source_id": "PARL_ACTS",
            "document_type": "Act",
            "title": "Industrial Disputes",
            "year": 1999,
            "authority_level": 2,
            "page_start": 1,
            "page_end": 3,
            "chunk_text": "32A No employer shall refuse...",
            "citation": "Industrial Disputes, No. 56 of 1999, pp. 1-3",
            "source_url": "https://example.test",
            "local_path": "data/example.pdf",
            "quality_flags": [],
            "metadata": {},
        },
        rank=1,
        signals=signals,
    )

    assert hit.retriever == "exact_citation_provision"
    assert hit.metadata["exact_citation_match"] is True
    assert hit.metadata["matched_provisions"] == ["32a"]


def test_case_name_signal_builds_title_and_citation_sql_clauses():
    signals = parse_exact_citation_signals("Perera v Silva.")
    sql, params = build_exact_sql(signals, RetrievalFilters(language=None))

    assert "rc.title ILIKE" in sql
    assert "rc.citation ILIKE" in sql
    assert params["case_left_0"] == "%Perera%"
    assert params["case_right_0"] == "%Silva%"
