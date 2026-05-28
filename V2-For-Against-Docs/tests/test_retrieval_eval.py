from __future__ import annotations

import pytest

from sl_legal_rag.retrieval_eval import (
    RetrievalEvalCase,
    assert_blind_cases_include_adverse,
    evaluate_retrieval_cases,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_retrieval_metric_functions_are_deterministic():
    expected = {"chunk_a", "chunk_c"}
    ranked = ["chunk_b", "chunk_a", "chunk_c"]

    assert recall_at_k(expected, ranked, 2) == 0.5
    assert reciprocal_rank(expected, ranked) == 0.5
    assert round(ndcg_at_k(expected, ranked, 3), 6) == 0.693426


def test_evaluate_retrieval_cases_reports_missing_queries():
    result = evaluate_retrieval_cases(
        [
            RetrievalEvalCase(
                query_id="q1",
                expected_chunk_ids=("chunk_a",),
                ranked_chunk_ids=("chunk_a", "chunk_b"),
            ),
            RetrievalEvalCase(
                query_id="q2",
                expected_chunk_ids=("chunk_missing",),
                ranked_chunk_ids=("chunk_x", "chunk_y"),
            ),
        ],
        k=2,
    )

    assert result.case_count == 2
    assert result.recall_at_k == 0.5
    assert result.mrr == 0.5
    assert result.missing_query_ids == ("q2",)
    assert not result.passes_minimum_bar


def test_evaluate_retrieval_cases_reports_supportive_and_adverse_recall():
    result = evaluate_retrieval_cases(
        [
            RetrievalEvalCase(
                query_id="supportive_1",
                expected_chunk_ids=("chunk_support",),
                ranked_chunk_ids=("chunk_support",),
                evidence_label="supportive",
            ),
            RetrievalEvalCase(
                query_id="adverse_1",
                expected_chunk_ids=("chunk_adverse",),
                ranked_chunk_ids=("chunk_other", "chunk_adverse"),
                evidence_label="adverse",
            ),
        ],
        k=1,
    )

    assert result.recall_by_label == {"adverse": 0.0, "supportive": 1.0}
    assert result.case_count_by_label == {"adverse": 1, "supportive": 1}


def test_blind_retrieval_eval_requires_adverse_authority_case():
    assert_blind_cases_include_adverse(
        [
            RetrievalEvalCase(
                query_id="adverse_1",
                expected_chunk_ids=("chunk_adverse",),
                ranked_chunk_ids=("chunk_adverse",),
                evidence_label="adverse",
            )
        ]
    )
    with pytest.raises(ValueError, match="adverse authority"):
        assert_blind_cases_include_adverse(
            [
                RetrievalEvalCase(
                    query_id="supportive_1",
                    expected_chunk_ids=("chunk_support",),
                    ranked_chunk_ids=("chunk_support",),
                    evidence_label="supportive",
                )
            ]
        )


def test_evaluate_retrieval_cases_empty_and_invalid_k():
    assert evaluate_retrieval_cases([]).case_count == 0
    with pytest.raises(ValueError, match="k must be at least 1"):
        evaluate_retrieval_cases([], k=0)
