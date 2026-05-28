# SL Legal Assist RAG / LLM Layer

This folder is the executable starting point for the LLM-facing retrieval system.
It is intentionally not an agent-first design. The core legal RAG path must be
auditable, deterministic where possible, citation-first, and bounded by a Legal
Research Pack before any strategy generation runs.

For the accuracy standard, see `rag/ACCURACY_FIRST_RAG.md`.
For enforceable product-safety foundations, see
`rag/sl_legal_rag/product_policy.py` and
`Docs/phase_reviews/phase_0_product_foundations_review.md`.

## Package Choice

Use OpenClaw-style agent skills only around the product edges, for example task
automation, inboxes, workflow helpers, or user-facing assistants. Do not use an
agent framework as the core retrieval authority layer.

Core stack:

- **PostgreSQL** for canonical document metadata, pages, legal units, chunks,
  citations, research packs, and audit logs.
- **OpenSearch** for BM25, phrase search, fuzzy search, filters, and hybrid rank
  fusion.
- **Qdrant** for dense vector search and optional sparse/hybrid vector search.
- **FastAPI + Pydantic** for typed APIs and strict research-pack contracts.
- **Ragas** for retrieval/answer evaluation once we have benchmark questions.
- **OpenAI embeddings** as the first embedding provider, with the schema storing
  model and dimensions so we can swap or compare local BGE/SPLADE models later.
- **Cross-encoder / late-interaction reranking** for precision after first-stage
  retrieval.
- **Docling or equivalent layout-aware extraction** for difficult PDFs where
  plain text extraction/OCR loses structure.

## Execution Order

1. Apply the PostgreSQL database schema:

   ```bash
   python3 scripts/apply_postgres_schema.py
   python3 scripts/check_postgres_schema.py
   ```

   The backend quality gate for repo-owned work is:

   ```bash
   uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
     --with pydantic-settings --with fastapi --with pytest --with httpx \
     --with eval-type-backport python scripts/run_quality_checks.py
   ```

   This compiles the package, scans for plaintext secrets, rejects unfinished
   work markers, checks the database schema, runs the rollback-only schema
   smoke test, and runs the test suite.

   Corpus manifests can be validated and imported into the database registry:

   ```bash
   PYTHONPATH=rag uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic \
     --with eval-type-backport python scripts/import_data_registry.py --dry-run
   ```

2. Build normalized chunks from the current manifest and extracted/OCR pages:

   ```bash
   python3 scripts/build_rag_chunks.py --limit 1000
   ```

3. Smoke-test research-pack creation locally:

   ```bash
   python3 scripts/query_rag_chunks_local.py "industrial disputes trade union bargaining" \
     --output data/indexes/sample_research_pack.json
   ```

   This local script is only for development. Production retrieval should use
   OpenSearch + Qdrant + RRF.

4. Start the local RAG services:

   ```bash
   docker compose -f docker-compose.rag.yml up -d
   ```

5. Load chunks into PostgreSQL, OpenSearch, and Qdrant. The first chunk builder
   writes `data/indexes/rag_chunks.jsonl`:

   ```bash
   python3 scripts/load_rag_chunks_postgres.py
   uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with eval-type-backport \
     python scripts/load_pages_postgres.py
   python3 scripts/load_rag_chunks_opensearch.py
   python3 scripts/load_rag_chunks_qdrant.py --provider auto
   ```

   Page loading reads manifest-referenced extracted/OCR page JSONL files and
   populates the `pages` table for documents already present in PostgreSQL.
   Production ingestion should also create an `ingestion_runs` row and
   `document_ingestion_events` rows through the repository layer, so every file
   acquisition, extraction, OCR, and indexing outcome has durable evidence while
   the `documents` table stores the current state.
   Extraction/OCR workers should score text with
   `rag.sl_legal_rag.extraction_quality` and block or flag low-confidence pages
   before those passages are used in legal-answer context.

   Existing research pack items can be anchored after pages are loaded:

   ```bash
   uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with eval-type-backport \
     python scripts/backfill_source_anchors.py
   ```

   `--provider auto` uses OpenAI embeddings when `OPENAI_API_KEY` is present,
   otherwise it uses a local sentence-transformer model. Production model choice
   must be based on retrieval evaluations.

6. Run a hybrid retrieval smoke query:

   ```bash
   uv run --with qdrant-client --with sentence-transformers \
     scripts/query_hybrid_retrieval.py "industrial disputes trade union bargaining"
   ```

7. Expose research-pack endpoints through `rag.sl_legal_rag.api`.

   The live endpoint is:

   ```text
   POST /v1/research/packs
   POST /v1/research/packs/{pack_id}/expand
   ```

   It runs exact citation/provision resolution first, then OpenSearch
   BM25/phrase/fuzzy retrieval plus Qdrant dense-vector retrieval, then fuses
   candidates into a typed Legal Research Pack. Each pack is sealed with a
   canonical hash, token count, source warnings, item scoring details, and a
   retrieval trace before it is persisted. The endpoint requires signed
   authentication for every request. When a request attaches the pack to a case,
   the authenticated user must also have case permission before retrieval is
   persisted. Expansion requests first verify access to the parent pack, then
   create a child pack with `parent_pack_id` and an incremented `pack_version`
   instead of rewriting the parent.

   Source-viewer contract:

   ```text
   GET /v1/research/packs/{pack_id}/items/{pack_item_id}/source
   ```

   It returns the cited document, citation, page range, selected text, source
   URL, resolved local PDF path, file-existence flag, page text when page-level
   extraction exists, and exact page anchors with character offsets when the
   selected pack text can be located. The endpoint always requires signed
   authentication; if the pack is linked to a case, the authenticated user must
   have permission on at least one linked case before source text, paths, or
   anchors are returned.

   Strategy validation contract:

   ```text
   POST /v1/strategy/validate
   ```

   It checks that every cited `pack_item_id` exists in the stored research pack.
   It checks citations from claims, answer text, counterarguments, and risk
   rankings. The endpoint requires signed authentication before it reads pack
   metadata. If the pack is linked to a case, the authenticated user must have
   permission on at least one linked case before item IDs are compared.

8. Generate and persist LLM strategy drafts only after `/v1/research/packs`
   returns cited, validated packs.

   The live endpoint is:

   ```text
   POST /v1/strategy/draft
   ```

   It requires a `case_id`, creates or validates an `agent_run`, generates a
   pack-bounded draft, saves the research pack, writes the draft, writes each
   cited legal claim, links claim citations to stored `research_pack_items`,
   includes source-anchor metadata where available, stores counterarguments,
   risk rankings, next-retrieval questions, and deterministic citation
   validation metadata, then creates lawyer-review items for the draft and
   claims. The strategy generator rejects out-of-pack citations, uncited legal
   claim sentences, prompt-injection attempts, and policy-blocked legal output
   before persistence.

   Prompt construction and case structuring contracts:

   ```text
   POST /v1/strategy/prompt
   POST /v1/cases/structure
   ```

   Both endpoints require signed authentication. `/v1/strategy/prompt` also
   checks case permission when a `case_id` is supplied. `/v1/cases/structure`
   handles raw case facts and runs the MECE structuring agent only after the
   signature is accepted.

   UI read endpoints for the persisted workflow:

   ```text
   GET /v1/cases/{case_id}/review/items
   GET /v1/cases/{case_id}/drafts
   GET /v1/cases/{case_id}/drafts/{draft_id}
   GET /v1/cases/{case_id}/claims
   GET /v1/cases/{case_id}/claims/{claim_id}
   GET /v1/cases/{case_id}/audit/events
   GET /v1/audit/events
   POST /v1/cases/{case_id}/review/items/{review_item_id}/decision
   ```

   These endpoints expose the lawyer-review queue, draft viewer data, claim
   lists, claim citation summaries, and source-viewer links back to the cited
   pack items. Case-scoped endpoints, source-viewer requests, strategy
   validation, prompt construction, case structuring, and research-pack creation
   require signed authentication headers:
   `X-SL-Legal-User-ID`, `X-SL-Legal-Auth-Timestamp`, and
   `X-SL-Legal-Auth-Signature`. The backend verifies the signature with
   `SL_LEGAL_AUTH_HMAC_SECRET`, then checks case permission for the authenticated
   user. Review decisions update the reviewed draft or claim and write an
   `audit_events` record.

   POST clients may also send `X-SL-Legal-Body-SHA256`. The signature is then
   calculated over that SHA-256 hex digest instead of requiring the verifier to
   derive the digest first. For accepted requests, the backend still compares the
   supplied digest with the actual request body. For oversized requests with a
   declared `Content-Length`, this lets the middleware authenticate and audit the
   rejection without reading the body.

   Authenticated AI and retrieval actions also write compact audit records:
   `research_pack.created`, `research_pack.source.viewed`,
   `strategy.prompt.built`, `case.structure.generated`, and
   `strategy.validation.checked`. Audit metadata stores hashes, counts, pack IDs,
   and case/user linkage; it does not store raw case facts, raw prompts, or source
   text. `/v1/audit/events` defaults to the authenticated user's own audit trail.
   `scope=organization` requires organization owner/admin audit access and may be
   filtered by `user_id`, `case_id`, `event_type`, `entity_type`, and `entity_id`.
   Audit listing uses keyset pagination: pass the returned `next_cursor` as the
   next request's `cursor` value. Cursor scans are supported by the
   `005_audit_indexes` migration.

   Expensive signed AI and retrieval endpoints enforce request-body limits and
   database-backed fixed-window rate limits before model or retrieval work runs.
   Defaults are intentionally conservative and can be configured with:

   ```text
   SL_LEGAL_RATE_LIMIT_WINDOW_SECONDS
   SL_LEGAL_RESEARCH_PACK_RATE_LIMIT
   SL_LEGAL_RESEARCH_PACK_EXPAND_RATE_LIMIT
   SL_LEGAL_STRATEGY_PROMPT_RATE_LIMIT
   SL_LEGAL_CASE_STRUCTURE_RATE_LIMIT
   SL_LEGAL_STRATEGY_DRAFT_RATE_LIMIT
   SL_LEGAL_STRATEGY_VALIDATE_RATE_LIMIT
   SL_LEGAL_RATE_LIMIT_RETENTION_SECONDS
   SL_LEGAL_METRICS_BEARER_TOKEN
   SL_LEGAL_RESEARCH_PACK_BODY_LIMIT_BYTES
   SL_LEGAL_STRATEGY_PROMPT_BODY_LIMIT_BYTES
   SL_LEGAL_CASE_STRUCTURE_BODY_LIMIT_BYTES
   SL_LEGAL_STRATEGY_DRAFT_BODY_LIMIT_BYTES
   SL_LEGAL_STRATEGY_VALIDATE_BODY_LIMIT_BYTES
   ```

   The `006_api_rate_limits` migration stores counters by authenticated user,
   route key, and time window. Blocked requests return `429` with
   `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
   `X-RateLimit-Reset` and write an `api.rate_limit.exceeded` audit event;
   authenticated oversized bodies return `413` and write an
   `api.request_body.too_large` audit event when `X-SL-Legal-Body-SHA256` and
   `Content-Length` are present.

   Operational guardrail metrics are available at:

   ```text
   GET /v1/operations/metrics
   GET /v1/operations/metrics/prometheus
   ```

   The JSON endpoint returns structured counters and latency summaries. The
   Prometheus endpoint returns text exposition for deployment monitoring. Both
   endpoints accept signed authentication from an active user. They also accept
   `Authorization: Bearer <token>` when `SL_LEGAL_METRICS_BEARER_TOKEN` is set
   to at least 32 characters for scraper integrations. Metrics include HTTP
   requests, HTTP errors, rate-limit rejections, oversized-body rejections,
   guardrail audit-write failures, and per-route latency summaries. Route labels
   use FastAPI route templates or bounded route groups so case IDs, pack IDs, and
   document IDs do not become metric labels.

   Rate-limit counters are operational data. Prune old windows on a schedule:

   ```bash
   uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with eval-type-backport \
     python scripts/prune_api_rate_limits.py
   ```

   Durable daily compliance rollups can be rebuilt from database-backed sources:

   ```bash
   uv run --with sqlalchemy --with 'psycopg[binary]' --with pydantic --with eval-type-backport \
     python scripts/rebuild_operational_rollups.py --date YYYY-MM-DD
   ```

   The rollup job writes `operational_metric_rollups` rows for guardrail audit
   events and signed route rate-limit windows. Rebuilding a day is idempotent.

9. Smoke-test the Azure-backed LLM boundary:

   ```bash
   uv run --with pydantic --with eval-type-backport \
     python scripts/smoke_test_mece_case_structuring.py

   uv run --with pydantic --with eval-type-backport \
     python scripts/smoke_test_pack_bounded_strategy.py
   ```

## Non-Negotiable LLM Boundary

The LLM is not allowed to answer legal questions directly from its general
knowledge. It receives:

- user case facts,
- a pack ID,
- selected `research_pack_items`,
- missing-source warnings,
- citation metadata,
- and instructions requiring every legal claim to cite a pack item.

If a claim cannot cite a pack item, the output must say the authority is not in
the current pack and request retrieval/verification.

Strategy generation also runs product-policy validation after pack-boundary
validation. Outputs are blocked if they present final legal advice, guarantee
outcomes, fabricate authority/evidence, hide adverse authority, tamper with
records, or bypass lawyer review.

## Azure OpenAI Chat Provider

Chat completion settings are read from environment variables or a local
`.env.azure-openai` file. That file is ignored by git.

```bash
python3 scripts/smoke_test_azure_openai.py
```

## Current Local Artifacts

- `rag/sql/001_core.sql`: core relational schema.
- `rag/sl_legal_rag/models.py`: typed research-pack and strategy models.
- `rag/sl_legal_rag/chunking.py`: legal chunk construction from page text.
- `rag/sl_legal_rag/retrieval.py`: RRF, authority boosts, and pack assembly.
- `scripts/build_rag_chunks.py`: manifest-to-chunks builder using existing
  extracted text and OCR outputs.
