# Accuracy-First Legal RAG Policy

This product must use the most reliable retrieval and citation methods we can
validate, not whichever RAG framework is easiest to wire. A legal strategy engine
is only as safe as the research pack that feeds it.

## Core Decision

Do not make OpenClaw, LangChain, LlamaIndex, or any agent framework the source of
truth for legal retrieval. These tools may help with orchestration, UI agents, or
workflow automation, but the retrieval core must remain explicit, testable, and
auditable.

The production legal RAG stack is:

1. **Layout-aware extraction**: PDF text layer, OCR, layout blocks, page numbers,
   tables, and quality flags.
2. **Legal-unit segmentation**: Acts by section/subsection, judgments by
   paragraphs/issues/holdings, gazettes by notice/order/regulation, Hansard by
   sitting/speaker/topic.
3. **Parent-child retrieval**: retrieve small citable chunks, then expand to the
   legal unit/page parent for context.
4. **Hybrid candidate retrieval**:
   - exact citation/provision lookup,
   - BM25 keyword search,
   - fuzzy lexical search,
   - dense vector search,
   - learned sparse retrieval where available,
   - citation graph expansion.
5. **Rank fusion**: combine candidate lists with Reciprocal Rank Fusion instead
   of trusting raw scores from different systems.
6. **Reranking**: use a cross-encoder or late-interaction reranker on the fused
   candidate pool before pack construction.
7. **Authority-aware legal scoring**: boost official sources, current law,
   higher courts, exact provision matches, and cited/followed authorities; penalize
   low-confidence OCR, missing page anchors, unofficial sources, and stale/repealed
   material.
8. **Legal Research Pack boundary**: the LLM can only reason from pack items.
9. **Evaluation gates**: every retrieval change must be tested on legal benchmark
   questions before it is trusted.

## Why This Matters

Legal search is unusually hostile to naive vector search:

- exact section numbers, case names, dates, and citations matter;
- small wording differences can change the legal result;
- higher authority can matter more than semantic similarity;
- old, repealed, amended, or unofficial material must be handled carefully;
- OCR errors can silently corrupt quotations and citations.

Therefore the default must be multi-stage retrieval, not “embed everything and
ask the LLM.”

## Production Retrieval Pipeline

```text
User query / case facts
        │
        ▼
Query planner
  - classify task
  - extract citations, statutes, sections, courts, dates, party names
  - create metadata filters
  - create retrieval-only query variants
        │
        ▼
Parallel candidate retrieval
  - exact citation/provision resolver
  - OpenSearch BM25 + phrase + fuzzy search
  - Qdrant dense vector search
  - learned sparse vector search where available
  - citation graph expansion
        │
        ▼
Candidate fusion
  - Reciprocal Rank Fusion
  - de-dup by legal unit and document
  - retain retrieval evidence
        │
        ▼
Reranking
  - cross-encoder reranker for query/chunk relevance
  - optional late-interaction reranker for hard questions
  - legal authority and source-quality scoring
        │
        ▼
Context shaping
  - parent legal unit expansion
  - exact page/citation anchors
  - token budget allocator
        │
        ▼
Legal Research Pack
  - immutable pack ID
  - pack items
  - missing-source warnings
  - retrieval trace
  - citation validation
        │
        ▼
LLM strategy/report generation
  - every legal claim cites pack_item_id
  - unsupported claims are rejected or flagged
```

## Recommended Models and Methods

Use these as candidates to evaluate, not as blindly trusted defaults.

| Layer | Primary candidate | Backup / comparison |
| --- | --- | --- |
| Dense embeddings | OpenAI `text-embedding-3-small` or larger model if evals justify cost | BGE-M3 / E5 family local embeddings |
| Sparse retrieval | OpenSearch BM25 | SPLADE-style learned sparse vectors or BGE-M3 sparse vectors |
| Rank fusion | Reciprocal Rank Fusion | DBSF / weighted fusion after evaluation |
| Reranking | BGE reranker v2 m3 or strong cross-encoder | ColBERT-style late interaction for difficult case-law retrieval |
| Extraction | Existing PDF text + OCR, then Docling/structured extraction for hard PDFs | manual review queue for low-confidence pages |
| Evaluation | Ragas + custom legal metrics + ranx IR metrics | lawyer-reviewed golden set |

## Evaluation Gates

No LLM legal strategy endpoint should be considered production-ready until these
metrics are measured and stable on a Sri Lankan legal benchmark set:

| Gate | Target |
| --- | --- |
| Citation/provision exact lookup | Near-perfect on known citations and section references |
| Retrieval Recall@20 | High recall for all known supporting authorities |
| nDCG@10 / MRR | Relevant authorities appear near the top |
| Unsupported legal claim rate | Zero tolerated in final answer validator |
| Citation hallucination rate | Zero tolerated |
| OCR page quality | Low-confidence pages excluded or flagged |
| Missing-source detection | Missing authorities are explicitly surfaced |
| Regression safety | New indexing changes cannot degrade benchmark results without review |

## Legal Pack Requirements

Each pack item must include:

- `pack_item_id`
- `document_id`
- `chunk_id`
- source title
- official/unofficial status where known
- authority level
- page range
- citation text
- source URL/local path
- selected passage
- retrieval scores
- reranker score
- source quality flags

The LLM receives pack items, not raw PDFs and not broad corpus access.

