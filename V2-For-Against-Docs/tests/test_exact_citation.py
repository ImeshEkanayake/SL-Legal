from __future__ import annotations

from sl_legal_rag.exact_citation import (
    ExactCitationSignals,
    ProvisionSignal,
    provision_signal_to_postgres_regex,
    row_to_search_hit,
)


def test_provision_only_article_regex_requires_article_prefix():
    provision = ProvisionSignal(kind="article", label="13", normalized_label="13")

    regex = provision_signal_to_postgres_regex(provision, require_kind_prefix=True)

    assert "article|articles|art" in regex
    assert "13" in regex


def test_act_scoped_provision_regex_can_match_label_only():
    provision = ProvisionSignal(kind="section", label="31(1)", normalized_label="31(1)")

    regex = provision_signal_to_postgres_regex(provision, require_kind_prefix=False)

    assert "section|sections" not in regex
    assert "31" in regex


def test_exact_citation_hit_carries_text_version_metadata():
    hit = row_to_search_hit(
        {
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "title": "Test Act",
            "document_type": "Act",
            "source_id": "PARL_ACTS",
            "authority_level": 2,
            "citation": "Test Act, p. 1",
            "chunk_text": "Article 13 text",
            "year": 2024,
            "page_start": 1,
            "page_end": 1,
            "source_url": "",
            "local_path": "",
            "quality_flags": [],
            "metadata": {},
            "text_version_id": "dtv_1",
            "text_origin": "source",
            "source_language": "English",
            "translated_from_language": None,
            "translation_review_status": None,
        },
        rank=1,
        signals=ExactCitationSignals(act_citations=(), provisions=(), case_names=()),
    )

    assert hit.metadata["text_version_id"] == "dtv_1"
    assert hit.metadata["text_origin"] == "source"
