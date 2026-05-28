#!/usr/bin/env python3
"""Exercise the SQLAlchemy repository layer against the live Postgres database.

The test runs inside one transaction and rolls back. It requires SQLAlchemy and
psycopg. Use:

  uv run --with sqlalchemy --with 'psycopg[binary]' scripts/smoke_test_db_access_layer.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from sqlalchemy.orm import Session  # noqa: E402

from sl_legal_rag.db import LegalWorkspaceRepository, database_health, make_engine  # noqa: E402


def main() -> int:
    engine = make_engine()
    health = database_health(engine)

    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, expire_on_commit=False, future=True)
        try:
            repo = LegalWorkspaceRepository(session)
            workspace = repo.create_case_workspace(
                organization_name="DB Access Smoke Legal Team",
                organization_slug=f"db-access-smoke-{id(session)}",
                user_email=f"db-access-smoke-{id(session)}@example.test",
                user_display_name="DB Access Smoke Lawyer",
                project_name="DB Access Smoke Project",
                case_title="DB Access Smoke Matter",
                case_number="SMOKE/DB/1",
                court="Supreme Court",
                matter_type="statutory_research",
            )
            raw_input_id = repo.add_case_raw_input(
                case_id=workspace.case_id,
                submitted_by_user_id=workspace.user_id,
                content="The employer refused to bargain with the trade union after workers asked for representation.",
            )
            chat = repo.create_chat_thread(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                created_by_user_id=workspace.user_id,
                title="Trade union bargaining research",
                first_user_message="Find the relevant legal authority about refusing to bargain with a trade union.",
            )
            agent_run_id = repo.create_agent_run(
                organization_id=workspace.organization_id,
                case_id=workspace.case_id,
                thread_id=chat.thread_id,
                agent_type="mece_case_structuring",
                model="db-access-smoke",
                input_payload={"raw_input_id": raw_input_id},
                output_payload={"status": "structured"},
            )
            repo.add_case_fact(
                case_id=workspace.case_id,
                raw_input_id=raw_input_id,
                fact_text="The employer refused to bargain with the trade union.",
                fact_category="material_fact",
                certainty_label="explicitly_stated",
                materiality="high",
                source_span_start=4,
                source_span_end=57,
                source_quote="employer refused to bargain with the trade union",
                extracted_by_agent_run_id=agent_run_id,
            )
            repo.add_case_issue(
                case_id=workspace.case_id,
                issue_text="Whether refusing to bargain with the trade union is an unfair labour practice.",
                issue_type="statutory_issue",
                inferred_reason="The fact pattern mentions refusal to bargain with a trade union.",
                created_by_agent_run_id=agent_run_id,
            )
            chunk = repo.first_retrieval_chunk()
            pack = repo.create_research_pack_with_chunk(
                case_id=workspace.case_id,
                thread_id=chat.thread_id,
                agent_run_id=agent_run_id,
                user_id=workspace.user_id,
                query="industrial disputes trade union bargaining",
                query_class="statute_lookup",
                chunk_id=str(chunk["chunk_id"]),
                selected_text=str(chunk["chunk_text"]),
            )
            claim_id = repo.add_supported_legal_claim(
                case_id=workspace.case_id,
                thread_id=chat.thread_id,
                message_id=chat.first_message_id,
                pack_id=pack.pack_id,
                agent_run_id=agent_run_id,
                claim_text="The research pack contains authority relevant to refusing to bargain with a trade union.",
                pack_item_ids=[pack.pack_item_id or ""],
            )
            repo.create_review_item(
                case_id=workspace.case_id,
                item_type="legal_claim",
                item_id=claim_id,
                assigned_to_user_id=workspace.user_id,
                priority="high",
            )
            overview = repo.case_overview(workspace.case_id)
            print(json.dumps({"health": health, "overview": overview}, indent=2))
        finally:
            session.close()
            transaction.rollback()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
