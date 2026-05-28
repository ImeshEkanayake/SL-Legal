# Retrieval Evaluation Plan

The system should earn trust through measured retrieval quality. We need a
Sri Lankan legal benchmark set before the LLM strategy layer is treated as
reliable.

## Golden Set Format

Create `rag/evals/golden_queries.jsonl` with one legal question per line:

```json
{
  "query_id": "industrial_disputes_union_bargaining_001",
  "query": "What law prevents an employer from refusing to bargain with a trade union representing at least 40% of workers?",
  "query_class": "statute_lookup",
  "expected_document_ids": ["parl_act_1999_056_g3752"],
  "expected_citations": ["Industrial Disputes (Amendment), No. 56 of 1999"],
  "must_include_terms": ["forty per centum", "refuse to bargain", "trade union"],
  "authority_level_required": [2],
  "notes": "Known answer-bearing provision from Act No. 56 of 1999."
}
```

## Metrics

- **Recall@k**: did the expected authority appear in top k?
- **MRR**: how high did the first correct authority rank?
- **nDCG@k**: are better authorities ranked higher?
- **Citation accuracy**: does each generated claim cite a real pack item?
- **Quote fidelity**: does quoted text match the source passage?
- **Missing-source accuracy**: does the system say when needed law is not in the
  corpus?
- **OCR risk rate**: how many selected passages come from low-confidence OCR?

## Required Test Buckets

- Exact Act and section lookups.
- Case-name and citation lookups.
- Fuzzy title/case-name queries with spelling mistakes.
- Legal concept queries with no exact citation.
- Date-sensitive statute/gazette questions.
- Court hierarchy questions.
- Questions where the correct answer is missing from the current corpus.
- OCR-heavy documents with known noisy text.

## Release Rule

The strategy engine must not be promoted until retrieval evals are passing and
the answer validator proves that every legal claim cites a pack item.
