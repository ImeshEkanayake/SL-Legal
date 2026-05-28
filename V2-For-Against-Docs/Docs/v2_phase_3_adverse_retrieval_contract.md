# V2 Phase 3 Adverse Retrieval Contract

## Purpose

Phase 3 makes adverse authority retrieval mandatory at the retrieval layer. V2 must not only retrieve material that supports the client position; it must also search for authorities that weaken, limit, contradict, or procedurally block the claim.

## Query Intents

Every V2 research request expands into five paired query intents:

- `supportive`: authorities that support or establish the claim.
- `adverse`: contrary or weakening authorities.
- `limitation`: statutory bars, time limits, thresholds, and limits.
- `exception`: exceptions, exemptions, qualifications, and carve-outs.
- `procedural_risk`: burden, jurisdiction, admissibility, procedure, and remedy risks.

Each intent has a deterministic query variant, purpose, expansion terms, and stable query variant ID.

## Retrieval Trace

Research packs now record:

- Original query and request purpose.
- Every query expansion with `query_intent`, `query_variant_id`, expanded query text, purpose, and expansion terms.
- Candidate counts by retriever.
- Candidate counts by query intent.
- Fusion method and reranker name.

Every selected pack item carries:

- `query_intent`
- `query_intents`
- `query_variant_ids`
- intent-tagged retrieval evidence such as `opensearch_bm25_phrase_fuzzy:limitation rank 1`
- page start and page end when available
- scoring breakdown fields for authority, recency, exactness, adverse relevance, and intent multiplier

## Scoring Features

The Phase 3 scoring layer is explainable and deterministic:

- `authority_score`: stronger for primary and higher-authority sources.
- `recency_score`: stronger for more recent authorities while preserving older foundational law.
- `exactness_score`: title, citation, text, and exact-citation signal overlap.
- `adverse_relevance_score`: adverse, limitation, exception, burden, jurisdiction, and procedural-risk term matches.
- `intent_score_multiplier`: combines those features and gives adverse-style intents an explicit retrieval-stage boost.

These features are stored in pack item metadata and scoring breakdowns. They do not replace lawyer review or claim-level assessment.

## Evaluation

The Phase 3 fixture lives at:

```text
rag/evals/v2_for_against_retrieval_fixture.json
```

Run the fixture gate:

```bash
PYTHONPATH=rag uv run --with pytest python scripts/run_v2_for_against_retrieval_eval.py
```

The fixture measures:

- overall recall
- supportive recall
- adverse recall
- case counts by label
- missing query IDs

Blind fixtures must include at least one adverse authority case. The default threshold requires both supportive and adverse recall to be at least `0.90`.

## Boundaries

- No strategy memo generation changes in Phase 3.
- No UI evidence stance panel changes in Phase 3.
- No database migration is applied.
- No V1 code or data is changed.
- Live corpus benchmark tuning remains a later operations task, but the fixture schema is ready for live ranked results.
