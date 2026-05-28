from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from sl_legal_rag.db import LegalWorkspaceRepository, make_engine
from sl_legal_rag.db.ids import new_id
from sl_legal_rag.models import ClaimEvidenceAssessmentRequest, LegalResearchPack, StrategyDraftResponse


def test_db_access_layer_vertical_workflow_rolls_back():
    engine = make_engine()
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False, future=True)
        try:
            repo = LegalWorkspaceRepository(session)
            workspace = repo.create_case_workspace(
                organization_name="Pytest Legal Team",
                organization_slug=f"pytest-legal-team-{id(session)}",
                user_email=f"pytest-{id(session)}@example.test",
                user_display_name="Pytest Lawyer",
                project_name="Pytest Project",
                case_title="Pytest Matter",
                case_number="PYTEST/1",
                court="Supreme Court",
                matter_type="statutory_research",
            )
            user_context = repo.user_context(workspace.user_id)
            assert user_context is not None
            assert user_context.organization_id == workspace.organization_id
            audit_event_id = repo.record_audit_event(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                user_id=workspace.user_id,
                event_type="pytest.audit.recorded",
                entity_type="pytest",
                entity_id="pytest_entity",
                after_state={"ok": True},
                metadata={"source": "test_db_access_layer"},
            )
            assert audit_event_id > 0
            assert repo.user_has_organization_audit_access(
                organization_id=workspace.organization_id,
                user_id=workspace.user_id,
            )
            audit_stream = repo.list_audit_events(
                organization_id=workspace.organization_id,
                user_id=workspace.user_id,
                event_type="pytest.audit.recorded",
            )
            assert len(audit_stream) == 1
            assert audit_stream[0]["audit_event_id"] == audit_event_id
            first_rate_limit = repo.consume_rate_limit(
                organization_id=workspace.organization_id,
                user_id=workspace.user_id,
                route_key="pytest.rate.limit",
                limit=1,
                window_seconds=3600,
            )
            assert first_rate_limit.allowed
            blocked_rate_limit = repo.consume_rate_limit(
                organization_id=workspace.organization_id,
                user_id=workspace.user_id,
                route_key="pytest.rate.limit",
                limit=1,
                window_seconds=3600,
            )
            assert not blocked_rate_limit.allowed
            today = datetime.now(timezone.utc).date()
            repo.record_audit_event(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                user_id=workspace.user_id,
                event_type="api.rate_limit.exceeded",
                entity_type="api_route",
                entity_id="pytest.guardrail.route",
                after_state={"route_key": "pytest.guardrail.route"},
            )
            repo.record_audit_event(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                user_id=workspace.user_id,
                event_type="api.request_body.too_large",
                entity_type="api_route",
                entity_id="pytest.guardrail.route",
                after_state={"route_key": "pytest.guardrail.route"},
            )
            rollup_result = repo.rebuild_daily_operational_rollups(rollup_date=today)
            assert rollup_result.upserted_count >= 3
            rollups = repo.list_operational_metric_rollups(rollup_date=today)
            assert any(
                row["metric_name"] == "guardrail_rate_limit_rejections_total"
                and row["source"] == "audit_events"
                and row["labels"]["route_key"] == "pytest.guardrail.route"
                and row["metric_value"] == 1
                for row in rollups
            )
            assert any(
                row["metric_name"] == "guardrail_request_body_too_large_total"
                and row["source"] == "audit_events"
                and row["labels"]["route_key"] == "pytest.guardrail.route"
                and row["metric_value"] == 1
                for row in rollups
            )
            assert any(
                row["metric_name"] == "rate_limit_window_requests_total"
                and row["source"] == "api_rate_limits"
                and row["labels"]["route_key"] == "pytest.rate.limit"
                and row["metric_value"] == 2
                for row in rollups
            )
            old_rate_limit_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
            session.execute(
                text(
                    """
                    INSERT INTO api_rate_limits (
                        organization_id, user_id, route_key, window_started_at,
                        window_seconds, request_count, last_request_at
                    )
                    VALUES (
                        :organization_id, :user_id, 'pytest.old.rate.limit',
                        :window_started_at, 3600, 7, :last_request_at
                    )
                    """
                ),
                {
                    "organization_id": workspace.organization_id,
                    "user_id": workspace.user_id,
                    "window_started_at": old_rate_limit_time,
                    "last_request_at": old_rate_limit_time,
                },
            )
            prune_result = repo.prune_expired_rate_limits(retention_seconds=60)
            assert prune_result.deleted_count >= 1
            remaining_old_rate_limits = session.execute(
                text("SELECT count(*) FROM api_rate_limits WHERE route_key = 'pytest.old.rate.limit'")
            ).scalar_one()
            assert remaining_old_rate_limits == 0
            ingestion_run_id = repo.start_ingestion_run(
                source_id="pytest.source",
                pipeline_name="pytest_ingestion_pipeline",
                pipeline_version="2026.05",
                manifest_path="data/manifests/pytest_manifest.csv",
                corpus_root="data/raw/pytest",
                input_manifest_hash="sha256:pytest-manifest",
                config={"ocr": "disabled_for_test"},
            )
            ingested_document_id = new_id("doc")
            ingestion_event = repo.record_document_ingestion_event(
                ingestion_run_id=ingestion_run_id,
                document_id=ingested_document_id,
                source_id="pytest.source",
                source_document_id="pytest-source-doc-001",
                document_type="pytest_legal_document",
                title="Pytest Ingested Legal Document",
                year=today.year,
                document_date=today,
                language="en",
                source_url="https://example.test/source-doc-001",
                download_url="https://example.test/source-doc-001.pdf",
                local_path="data/raw/pytest/source-doc-001.pdf",
                file_hash="sha256:pytest-file",
                acquisition_status="downloaded",
                extraction_status="extracted",
                stage="page_extraction",
                status="extracted",
                extraction_method="pytest_text_layer",
                ocr_required=False,
                page_count=3,
                chunk_count=2,
                text_hash="sha256:pytest-text",
                text_quality_score=0.98,
                quality_flags=[],
                legal_status="current",
                next_action="Load chunks into search indexes.",
                metadata={"fixture": "db_access_layer"},
                version_label="pytest-v1",
                source_snapshot={"manifest_row": 1},
            )
            assert ingestion_event.document_id == ingested_document_id
            assert ingestion_event.status == "extracted"
            failed_document_id = new_id("doc")
            repo.record_document_ingestion_event(
                ingestion_run_id=ingestion_run_id,
                document_id=failed_document_id,
                source_id="pytest.source",
                source_document_id="pytest-source-doc-002",
                document_type="pytest_legal_document",
                title="Pytest Failed Legal Document",
                acquisition_status="download_failed",
                extraction_status="failed",
                stage="download",
                status="failed",
                local_path="data/raw/pytest/source-doc-002.pdf",
                error_code="pytest_download_failed",
                error_message="Download failed inside rollback-only test.",
                missing_reason="source returned a test failure",
                next_action="Retry from official source.",
            )
            ingestion_summary = repo.finish_ingestion_run(
                ingestion_run_id=ingestion_run_id,
                status="complete",
                output={"indexed": 1, "failed": 1},
            )
            assert ingestion_summary.status == "complete"
            assert ingestion_summary.document_count == 2
            assert ingestion_summary.page_count == 3
            assert ingestion_summary.chunk_count == 2
            assert ingestion_summary.error_count == 1
            stored_run = repo.get_ingestion_run(ingestion_run_id)
            assert stored_run is not None
            assert stored_run["output"]["indexed"] == 1
            failed_events = repo.list_document_ingestion_events(
                ingestion_run_id=ingestion_run_id,
                status="failed",
            )
            assert len(failed_events) == 1
            assert failed_events[0]["error_code"] == "pytest_download_failed"
            current_document = session.execute(
                text(
                    """
                    SELECT
                        current_ingestion_run_id, extraction_status,
                        text_quality_score, last_ingested_at
                    FROM documents
                    WHERE document_id = :document_id
                    """
                ),
                {"document_id": ingested_document_id},
            ).mappings().one()
            assert current_document["current_ingestion_run_id"] == ingestion_run_id
            assert current_document["extraction_status"] == "extracted"
            assert float(current_document["text_quality_score"]) == 0.98
            assert current_document["last_ingested_at"] is not None
            version_run_id = session.execute(
                text(
                    """
                    SELECT ingestion_run_id
                    FROM document_versions
                    WHERE document_id = :document_id
                      AND version_label = 'pytest-v1'
                    """
                ),
                {"document_id": ingested_document_id},
            ).scalar_one()
            assert version_run_id == ingestion_run_id
            missing_source_id = repo.upsert_missing_source_record(
                external_missing_id="PYTEST-MISSING-001",
                source_id="pytest.source",
                category="Historical Court Material",
                title="Pre-online pytest court record gap",
                reason="Historical pytest court records are incomplete.",
                next_action="Locate archival pytest scans.",
                priority="critical",
                status="open",
                expected_coverage="1948-present",
                known_available_coverage="current online records",
                legal_importance="critical",
                risk_if_missing="Binding authority may be missed.",
                probable_source="Court registry",
                owner="Corpus lead",
                last_checked=datetime.now(timezone.utc),
                notes="Inserted by rollback-only DB access test.",
            )
            assert missing_source_id > 0
            updated_missing_source_id = repo.upsert_missing_source_record(
                external_missing_id="PYTEST-MISSING-001",
                source_id="pytest.source",
                category="Historical Court Material",
                title="Pre-online pytest court record gap",
                reason="Historical pytest court records are incomplete.",
                next_action="Retry official archive request.",
                priority="critical",
                status="open",
            )
            assert updated_missing_source_id == missing_source_id
            missing_next_action = session.execute(
                text(
                    """
                    SELECT next_action
                    FROM missing_sources
                    WHERE external_missing_id = 'PYTEST-MISSING-001'
                    """
                )
            ).scalar_one()
            assert missing_next_action == "Retry official archive request."
            raw_input_id = repo.add_case_raw_input(
                case_id=workspace.case_id,
                submitted_by_user_id=workspace.user_id,
                content="The employer refused to bargain with the trade union.",
            )
            chat = repo.create_chat_thread(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                created_by_user_id=workspace.user_id,
                title="Pytest chat",
                first_user_message="Find the authority.",
            )
            agent_run_id = repo.create_agent_run(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                thread_id=chat.thread_id,
                agent_type="mece_case_structuring",
                model="pytest",
            )
            repo.add_case_fact(
                case_id=workspace.case_id,
                raw_input_id=raw_input_id,
                fact_text="The employer refused to bargain with the trade union.",
                fact_category="material_fact",
                certainty_label="explicitly_stated",
                extracted_by_agent_run_id=agent_run_id,
            )
            repo.add_case_issue(
                case_id=workspace.case_id,
                issue_text="Whether refusal to bargain is legally prohibited.",
                issue_type="statutory_issue",
                created_by_agent_run_id=agent_run_id,
            )
            seed_document_id = new_id("doc")
            seed_chunk_id = new_id("chunk")
            session.execute(
                text(
                    """
                    INSERT INTO documents (
                        document_id, source_id, document_type, title, year,
                        language, acquisition_status, extraction_status, legal_status
                    )
                    VALUES (
                        :document_id, 'pytest.source', 'Act',
                        'Pytest Seed Retrieval Act', 2099, 'English',
                        'downloaded', 'text_extracted', 'test_fixture'
                    )
                    """
                ),
                {"document_id": seed_document_id},
            )
            session.execute(
                text(
                    """
                    INSERT INTO retrieval_chunks (
                        chunk_id, document_id, source_id, document_type, title,
                        year, authority_level, page_start, page_end, chunk_index,
                        chunk_text, token_estimate, language, citation, text_hash
                    )
                    VALUES (
                        :chunk_id, :document_id, 'pytest.source', 'Act',
                        'Pytest Seed Retrieval Act', 2099, 1, 1, 1, 1,
                        'No employer shall refuse to bargain with a qualifying trade union.',
                        12, 'English', 'Pytest Seed Retrieval Act s 1',
                        'sha256:pytest-seed-chunk'
                    )
                    """
                ),
                {"chunk_id": seed_chunk_id, "document_id": seed_document_id},
            )
            session.execute(
                text(
                    """
                    INSERT INTO pages (
                        page_id, document_id, page_number, text, text_hash,
                        extraction_method, ocr_confidence, quality_flags
                    )
                    VALUES (
                        :page_id, :document_id, 1,
                        'No employer shall refuse to bargain with a qualifying trade union.',
                        'sha256:pytest-seed-page', 'pytest_text_layer', 0.99, '{}'
                    )
                    """
                ),
                {"page_id": new_id("page"), "document_id": seed_document_id},
            )
            chunk = repo.first_retrieval_chunk()
            assert chunk["chunk_id"] == seed_chunk_id
            pack_id = new_id("pack")
            pack_model = LegalResearchPack.model_validate(
                {
                    "pack_id": pack_id,
                    "query": "industrial disputes trade union bargaining",
                    "query_class": "statute_lookup",
                    "filters": {},
                    "retrieval_config": {
                        "fusion": "reciprocal_rank_fusion",
                        "max_tokens": 12000,
                        "retriever_counts": {
                            "opensearch_bm25_phrase_fuzzy": 1,
                            "qdrant_dense_vector": 0,
                        },
                    },
                    "items": [
                        {
                            "pack_item_id": f"{pack_id}_item_001",
                            "chunk_id": str(chunk["chunk_id"]),
                            "document_id": str(chunk["document_id"]),
                            "title": str(chunk["title"]),
                            "document_type": "Act",
                            "source_id": "PARL_ACTS",
                            "authority_level": 2,
                            "citation": str(chunk["citation"]),
                            "page_start": chunk["page_start"],
                            "page_end": chunk["page_end"],
                            "text": str(chunk["chunk_text"]),
                            "fused_score": 1.0,
                            "selection_reason": "integration test selected first retrieval chunk",
                        }
                    ],
                }
            )
            persisted_pack = repo.save_research_pack(
                pack=pack_model,
                case_id=workspace.case_id,
                source_thread_id=chat.thread_id,
                source_agent_run_id=agent_run_id,
                created_by_user_id=workspace.user_id,
            )
            repeated_pack = repo.save_research_pack(
                pack=pack_model,
                case_id=workspace.case_id,
                source_thread_id=chat.thread_id,
                source_agent_run_id=agent_run_id,
                created_by_user_id=workspace.user_id,
            )
            assert repeated_pack.pack_hash == persisted_pack.pack_hash
            with pytest.raises(ValueError, match="immutability violation"):
                repo.save_research_pack(
                    pack=pack_model.model_copy(update={"query": "changed legal research question"}),
                    case_id=workspace.case_id,
                    source_thread_id=chat.thread_id,
                    source_agent_run_id=agent_run_id,
                    created_by_user_id=workspace.user_id,
                )
            pack_access_context = repo.research_pack_access_context(persisted_pack.pack_id)
            assert pack_access_context is not None
            assert pack_access_context.case_ids == (workspace.case_id,)
            source = repo.get_pack_item_source(
                pack_id=persisted_pack.pack_id,
                pack_item_id=pack_model.items[0].pack_item_id,
            )
            assert source is not None
            assert source.pack_id == persisted_pack.pack_id
            assert source.pack_item_id == pack_model.items[0].pack_item_id
            assert source.chunk_id == str(chunk["chunk_id"])
            assert source.page_start == chunk["page_start"]
            assert source.page_end == chunk["page_end"]
            assert source.context_source in {"research_pack_item", "page_text"}
            assert source.selected_text
            strategy_response = StrategyDraftResponse.model_validate(
                {
                    "pack_id": persisted_pack.pack_id,
                    "answer": "A pack-bounded legal claim. "
                    f"[{pack_model.items[0].pack_item_id}]",
                    "claims": [
                        {
                            "claim": "A pack-bounded legal claim.",
                            "pack_item_ids": [pack_model.items[0].pack_item_id],
                            "confidence": "needs_lawyer_review",
                        }
                    ],
                    "missing_authorities": ["Adverse authority search should be completed before final advice."],
                    "warnings": ["Lawyer review required."],
                }
            )
            persisted_strategy = repo.persist_strategy_draft(
                case_id=workspace.case_id,
                thread_id=chat.thread_id,
                parent_message_id=chat.first_message_id,
                agent_run_id=agent_run_id,
                created_by_user_id=workspace.user_id,
                assigned_review_user_id=workspace.user_id,
                requested_output="strategy_report",
                research_pack=pack_model,
                strategy_response=strategy_response,
            )
            assert persisted_strategy.draft_id.startswith("draft_")
            assert persisted_strategy.message_id is not None
            assert len(persisted_strategy.claim_ids) == 1
            assert persisted_strategy.draft_review_item_id.startswith("review_")
            assert len(persisted_strategy.claim_review_item_ids) == 1

            follow_up_message = repo.add_case_user_message(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                user_id=workspace.user_id,
                content="Check whether the source anchor is visible.",
            )
            assert follow_up_message["threadId"] == chat.thread_id
            assert follow_up_message["content"] == "Check whether the source anchor is visible."

            created_case = repo.create_case_for_user(
                user_id=workspace.user_id,
                title="Pytest Related Matter",
                project_id=workspace.project_id,
                case_number="PYTEST/2",
            )
            assert created_case.project_id == workspace.project_id
            assert repo.user_has_case_permission(case_id=created_case.case_id, user_id=workspace.user_id)

            workspace_snapshot = repo.case_workspace_snapshot(case_id=workspace.case_id, user_id=workspace.user_id)
            assert workspace_snapshot["activeCaseId"] == workspace.case_id
            assert any(item["caseId"] == created_case.case_id for item in workspace_snapshot["cases"])
            assert any(item["content"] == "Check whether the source anchor is visible." for item in workspace_snapshot["messages"])
            assert any(item["documentId"] == seed_document_id for item in workspace_snapshot["documents"])
            assert workspace_snapshot["researchPackItems"][0]["packItemId"] == pack_model.items[0].pack_item_id
            assert workspace_snapshot["researchPackItems"][0]["anchors"][0]["quote"]
            assert workspace_snapshot["drafts"][0]["draftId"] == persisted_strategy.draft_id
            assert {item["itemType"] for item in workspace_snapshot["reviewItems"]} == {"draft", "legal_claim"}

            review_items = repo.list_review_items(case_id=workspace.case_id, status="pending")
            assert {item["item_type"] for item in review_items} == {"draft", "legal_claim"}
            assert all(item["item_title"] for item in review_items)

            drafts = repo.list_case_drafts(case_id=workspace.case_id)
            assert len(drafts) == 1
            assert drafts[0]["draft_id"] == persisted_strategy.draft_id
            assert drafts[0]["claim_count"] == 1
            assert drafts[0]["review_status"] == "pending"

            draft_detail = repo.get_draft_detail(case_id=workspace.case_id, draft_id=persisted_strategy.draft_id)
            assert draft_detail is not None
            assert draft_detail["content_markdown"] == strategy_response.answer
            assert len(draft_detail["claims"]) == 1
            assert draft_detail["review_items"][0]["review_item_id"] == persisted_strategy.draft_review_item_id

            claims = repo.list_case_claims(case_id=workspace.case_id, draft_id=persisted_strategy.draft_id)
            assert len(claims) == 1
            assert claims[0]["claim_id"] == persisted_strategy.claim_ids[0]
            assert claims[0]["citation_count"] == 1

            claim_detail = repo.get_claim_detail(case_id=workspace.case_id, claim_id=persisted_strategy.claim_ids[0])
            assert claim_detail is not None
            assert claim_detail["citations"][0]["pack_item_id"] == pack_model.items[0].pack_item_id
            assert claim_detail["citations"][0]["source_endpoint"].endswith("/source")
            assert claim_detail["review_items"][0]["review_item_id"] == persisted_strategy.claim_review_item_ids[0]

            supporting_assessment = repo.add_claim_evidence_assessment(
                case_id=workspace.case_id,
                assessment=ClaimEvidenceAssessmentRequest.model_validate(
                    {
                        "claim_id": persisted_strategy.claim_ids[0],
                        "pack_id": persisted_pack.pack_id,
                        "pack_item_id": pack_model.items[0].pack_item_id,
                        "stance": "supports_claim",
                        "rationale": "The source directly supports the pack-bounded claim.",
                        "confidence_score": 0.91,
                        "risk_level": "medium",
                        "source_quote": "No employer shall refuse to bargain with a qualifying trade union.",
                        "page_start": 1,
                        "page_end": 1,
                    }
                ),
                created_by_user_id=workspace.user_id,
            )
            adverse_assessment = repo.add_claim_evidence_assessment(
                case_id=workspace.case_id,
                assessment=ClaimEvidenceAssessmentRequest.model_validate(
                    {
                        "claim_text": "The employer can argue the union was not qualifying.",
                        "pack_id": persisted_pack.pack_id,
                        "pack_item_id": pack_model.items[0].pack_item_id,
                        "stance": "contradicts_claim",
                        "rationale": "The same item is adverse to a different claim because the duty depends on qualification.",
                        "confidence_score": 0.78,
                        "risk_level": "high",
                        "source_quote": "qualifying trade union",
                        "page_start": 1,
                        "page_end": 1,
                    }
                ),
                created_by_user_id=workspace.user_id,
            )
            assert supporting_assessment["stance"] == "supports_claim"
            assert adverse_assessment["stance"] == "contradicts_claim"
            assert supporting_assessment["pack_item_id"] == adverse_assessment["pack_item_id"]
            assert supporting_assessment["claim_id"] != adverse_assessment["claim_id"]

            grouped_assessments = repo.grouped_claim_evidence_assessments(case_id=workspace.case_id)
            assert grouped_assessments["total_count"] == 2
            assessment_counts = {
                group["stance"]: group["count"]
                for group in grouped_assessments["groups"]
            }
            assert assessment_counts["supports_claim"] == 1
            assert assessment_counts["contradicts_claim"] == 1

            claim_review = repo.apply_review_decision(
                case_id=workspace.case_id,
                review_item_id=persisted_strategy.claim_review_item_ids[0],
                reviewer_user_id=workspace.user_id,
                decision="approved",
                comment="Reviewed against cited source.",
            )
            assert claim_review is not None
            assert claim_review.target_status == "lawyer_approved"
            assert claim_review.review_item["status"] == "approved"
            approved_claim = repo.get_claim_detail(
                case_id=workspace.case_id,
                claim_id=persisted_strategy.claim_ids[0],
            )
            assert approved_claim is not None
            assert approved_claim["support_status"] == "lawyer_approved"
            assert approved_claim["reviewed_by_user_id"] == workspace.user_id

            draft_review = repo.apply_review_decision(
                case_id=workspace.case_id,
                review_item_id=persisted_strategy.draft_review_item_id,
                reviewer_user_id=workspace.user_id,
                decision="changes_requested",
                comment="Add adverse authority research before approval.",
            )
            assert draft_review is not None
            assert draft_review.target_status == "changes_requested"
            changed_draft = repo.get_draft_detail(case_id=workspace.case_id, draft_id=persisted_strategy.draft_id)
            assert changed_draft is not None
            assert changed_draft["status"] == "changes_requested"
            assert changed_draft["review_status"] == "changes_requested"
            assert repo.list_review_items(case_id=workspace.case_id, status="pending") == []

            audit_count = session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM audit_events
                    WHERE case_id = :case_id
                      AND event_type = 'review.decision.recorded'
                    """
                ),
                {"case_id": workspace.case_id},
            ).scalar_one()
            assert audit_count == 2
            audit_events = repo.list_case_audit_events(
                case_id=workspace.case_id,
                event_type="review.decision.recorded",
            )
            assert len(audit_events) == 2
            assert audit_events[0]["metadata"]["target_status"] in {"changes_requested", "lawyer_approved"}
            assert audit_events[0]["before_state"]["review_item"]["status"] == "pending"

            overview = repo.case_overview(workspace.case_id)
            assert overview["fact_count"] == 1
            assert overview["issue_count"] == 1
            assert overview["thread_count"] == 1
            assert overview["pack_count"] == 1
            assert overview["claim_count"] == 2
            assert overview["review_count"] == 2
        finally:
            session.close()
            transaction.rollback()
