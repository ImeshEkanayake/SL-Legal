from __future__ import annotations

from sl_legal_rag.source_anchoring import PageText, build_source_anchors


def test_build_source_anchors_splits_exact_context_across_pages():
    pages = [
        PageText(page_id="page_1", page_number=1, text="Alpha text"),
        PageText(page_id="page_2", page_number=2, text="Beta text"),
    ]

    anchors = build_source_anchors(
        pack_id="pack_1",
        pack_item_id="pack_1_item_001",
        chunk_id="chunk_1",
        document_id="doc_1",
        selected_text="Alpha text\n\nBeta text",
        pages=pages,
    )

    assert len(anchors) == 2
    assert anchors[0].page_number == 1
    assert anchors[0].char_start == 0
    assert anchors[0].char_end == len("Alpha text")
    assert anchors[0].match_method == "exact_context"
    assert anchors[1].page_number == 2


def test_build_source_anchors_handles_normalized_whitespace():
    pages = [PageText(page_id="page_1", page_number=1, text="No employer shall\nrefuse   to bargain.")]

    anchors = build_source_anchors(
        pack_id="pack_1",
        pack_item_id="pack_1_item_001",
        chunk_id="chunk_1",
        document_id="doc_1",
        selected_text="No employer shall refuse to bargain.",
        pages=pages,
    )

    assert len(anchors) == 1
    assert anchors[0].match_method == "normalized_context"
    assert anchors[0].confidence == 0.95
    assert anchors[0].quote == "No employer shall\nrefuse   to bargain."
