from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import (
    AgentResearchPlan,
    ClaimEvidenceAssessment,
    ClaimEvidenceAssessmentRequest,
    EvidenceStance,
    LegalResearchPack,
    MatterMemory,
    PackItemSourceResponse,
    StrategyDraftResponse,
    citation_role_for_evidence_stance,
    evidence_stance_for_citation_role,
)
from ..research_pack import research_pack_hash as canonical_research_pack_hash
from ..research_pack import require_valid_research_pack_contract, seal_research_pack
from ..source_anchoring import PageText, SourceAnchor, build_source_anchors
from .ids import new_id


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CASE_FILE_CACHE_ROOT_ENV = "SL_LEGAL_CASE_FILE_CACHE_ROOT"
CASE_FILE_CACHE_MAX_BYTES_ENV = "SL_LEGAL_CASE_FILE_CACHE_MAX_BYTES"
CASE_FILE_CACHE_TIMEOUT_SECONDS_ENV = "SL_LEGAL_CASE_FILE_CACHE_TIMEOUT_SECONDS"
CASE_FILE_CACHE_ALLOWED_HOSTS_ENV = "SL_LEGAL_CASE_FILE_ALLOWED_HOSTS"
DEFAULT_CASE_FILE_CACHE_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_CASE_FILE_CACHE_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CaseWorkspaceIds:
    organization_id: str
    user_id: str
    project_id: str
    case_id: str


@dataclass(frozen=True)
class ChatThreadIds:
    thread_id: str
    first_message_id: str


@dataclass(frozen=True)
class CreatedCaseIds:
    case_id: str
    project_id: str


@dataclass(frozen=True)
class ResearchPackIds:
    pack_id: str
    pack_item_id: str | None


@dataclass(frozen=True)
class PersistedResearchPack:
    pack_id: str
    item_count: int
    pack_hash: str


@dataclass(frozen=True)
class ResearchPackAccessContext:
    pack_id: str
    case_ids: tuple[str, ...]


@dataclass(frozen=True)
class UserContext:
    user_id: str
    organization_id: str | None


@dataclass(frozen=True)
class CaseContext:
    case_id: str
    organization_id: str
    created_by_user_id: str | None


@dataclass(frozen=True)
class PersistedStrategyDraft:
    draft_id: str
    message_id: str | None
    agent_run_id: str
    claim_ids: list[str]
    draft_review_item_id: str
    claim_review_item_ids: list[str]
    reasoning_review_item_ids: list[str]


@dataclass(frozen=True)
class ReviewDecisionResult:
    review_item: dict[str, Any]
    target_item_type: str
    target_item_id: str
    target_status: str
    audit_event_id: int


@dataclass(frozen=True)
class RateLimitResult:
    route_key: str
    request_count: int
    limit: int
    window_seconds: int
    window_started_at: datetime
    resets_at: datetime
    retry_after_seconds: int

    @property
    def allowed(self) -> bool:
        return self.request_count <= self.limit


@dataclass(frozen=True)
class RateLimitPruneResult:
    retention_seconds: int
    cutoff: datetime
    deleted_count: int


@dataclass(frozen=True)
class OperationalRollupResult:
    rollup_date: date
    source: str
    upserted_count: int


@dataclass(frozen=True)
class IngestionRunSummary:
    ingestion_run_id: str
    status: str
    document_count: int
    page_count: int
    chunk_count: int
    error_count: int


@dataclass(frozen=True)
class DocumentIngestionEventResult:
    ingestion_event_id: int
    document_id: str
    status: str
    stage: str


class LegalWorkspaceRepository:
    """Repository for the first production vertical slice.

    This class keeps app code away from raw SQL details while preserving explicit
    database contracts. Methods flush but do not commit; callers own the
    transaction boundary.
    """

    def __init__(self, session: Session):
        self.session = session

    def create_case_workspace(
        self,
        *,
        organization_name: str,
        organization_slug: str,
        user_email: str,
        user_display_name: str,
        project_name: str,
        case_title: str,
        case_number: str | None = None,
        court: str | None = None,
        matter_type: str | None = None,
    ) -> CaseWorkspaceIds:
        organization_id = new_id("org")
        user_id = new_id("user")
        project_id = new_id("project")
        case_id = new_id("case")

        self.session.execute(
            text(
                """
                INSERT INTO organizations (organization_id, name, slug)
                VALUES (:organization_id, :name, :slug)
                """
            ),
            {"organization_id": organization_id, "name": organization_name, "slug": organization_slug},
        )
        self.session.execute(
            text(
                """
                INSERT INTO app_users (user_id, organization_id, email, display_name, role)
                VALUES (:user_id, :organization_id, :email, :display_name, 'lawyer')
                """
            ),
            {
                "user_id": user_id,
                "organization_id": organization_id,
                "email": user_email,
                "display_name": user_display_name,
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO organization_memberships (organization_id, user_id, role)
                VALUES (:organization_id, :user_id, 'owner')
                """
            ),
            {"organization_id": organization_id, "user_id": user_id},
        )
        self.session.execute(
            text(
                """
                INSERT INTO projects (project_id, organization_id, name, created_by_user_id)
                VALUES (:project_id, :organization_id, :name, :created_by_user_id)
                """
            ),
            {
                "project_id": project_id,
                "organization_id": organization_id,
                "name": project_name,
                "created_by_user_id": user_id,
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO cases (
                    case_id, organization_id, project_id, case_number, title,
                    jurisdiction, court, matter_type, created_by_user_id
                )
                VALUES (
                    :case_id, :organization_id, :project_id, :case_number, :title,
                    'Sri Lanka', :court, :matter_type, :created_by_user_id
                )
                """
            ),
            {
                "case_id": case_id,
                "organization_id": organization_id,
                "project_id": project_id,
                "case_number": case_number,
                "title": case_title,
                "court": court,
                "matter_type": matter_type,
                "created_by_user_id": user_id,
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO case_permissions (case_id, user_id, role, granted_by_user_id)
                VALUES (:case_id, :user_id, 'owner', :user_id)
                """
            ),
            {"case_id": case_id, "user_id": user_id},
        )
        self.session.flush()
        return CaseWorkspaceIds(
            organization_id=organization_id,
            user_id=user_id,
            project_id=project_id,
            case_id=case_id,
        )

    def create_case_for_user(
        self,
        *,
        user_id: str,
        title: str,
        project_id: str | None = None,
        project_name: str | None = None,
        case_number: str | None = None,
        court: str | None = None,
        matter_type: str | None = None,
    ) -> CreatedCaseIds:
        user_context = self.user_context(user_id)
        if user_context is None:
            raise PermissionError(f"Authenticated user is not active: {user_id}")
        if user_context.organization_id is None:
            raise PermissionError("Authenticated user is not attached to an organization")

        organization_id = user_context.organization_id
        resolved_project_id = project_id
        if resolved_project_id:
            project_row = self.session.execute(
                text(
                    """
                    SELECT project_id
                    FROM projects
                    WHERE project_id = :project_id
                      AND organization_id = :organization_id
                      AND status = 'active'
                    """
                ),
                {"project_id": resolved_project_id, "organization_id": organization_id},
            ).mappings().first()
            if project_row is None:
                raise ValueError(f"Project not found in the user's organization: {resolved_project_id}")
        else:
            if not project_name:
                raise ValueError("project_name is required when project_id is not supplied")
            resolved_project_id = new_id("project")
            self.session.execute(
                text(
                    """
                    INSERT INTO projects (project_id, organization_id, name, created_by_user_id)
                    VALUES (:project_id, :organization_id, :name, :created_by_user_id)
                    """
                ),
                {
                    "project_id": resolved_project_id,
                    "organization_id": organization_id,
                    "name": project_name,
                    "created_by_user_id": user_id,
                },
            )

        case_id = new_id("case")
        self.session.execute(
            text(
                """
                INSERT INTO cases (
                    case_id, organization_id, project_id, case_number, title,
                    jurisdiction, court, matter_type, created_by_user_id
                )
                VALUES (
                    :case_id, :organization_id, :project_id, :case_number, :title,
                    'Sri Lanka', :court, :matter_type, :created_by_user_id
                )
                """
            ),
            {
                "case_id": case_id,
                "organization_id": organization_id,
                "project_id": resolved_project_id,
                "case_number": case_number,
                "title": title,
                "court": court,
                "matter_type": matter_type,
                "created_by_user_id": user_id,
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO case_permissions (case_id, user_id, role, granted_by_user_id)
                VALUES (:case_id, :user_id, 'owner', :user_id)
                """
            ),
            {"case_id": case_id, "user_id": user_id},
        )
        self.session.flush()
        return CreatedCaseIds(case_id=case_id, project_id=resolved_project_id)

    def add_case_raw_input(
        self,
        *,
        case_id: str,
        submitted_by_user_id: str,
        content: str,
        input_type: str = "user_case_facts",
    ) -> str:
        raw_input_id = new_id("raw")
        self.session.execute(
            text(
                """
                INSERT INTO case_raw_inputs (
                    raw_input_id, case_id, input_type, content, submitted_by_user_id
                )
                VALUES (:raw_input_id, :case_id, :input_type, :content, :submitted_by_user_id)
                """
            ),
            {
                "raw_input_id": raw_input_id,
                "case_id": case_id,
                "input_type": input_type,
                "content": content,
                "submitted_by_user_id": submitted_by_user_id,
            },
        )
        self.session.flush()
        return raw_input_id

    def create_chat_thread(
        self,
        *,
        organization_id: str,
        case_id: str,
        created_by_user_id: str,
        title: str,
        first_user_message: str,
    ) -> ChatThreadIds:
        thread_id = new_id("thread")
        message_id = new_id("msg")
        self.session.execute(
            text(
                """
                INSERT INTO chat_threads (
                    thread_id, organization_id, case_id, title, created_by_user_id
                )
                VALUES (:thread_id, :organization_id, :case_id, :title, :created_by_user_id)
                """
            ),
            {
                "thread_id": thread_id,
                "organization_id": organization_id,
                "case_id": case_id,
                "title": title,
                "created_by_user_id": created_by_user_id,
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO chat_messages (
                    message_id, thread_id, role, content, created_by_user_id
                )
                VALUES (:message_id, :thread_id, 'user', :content, :created_by_user_id)
                """
            ),
            {
                "message_id": message_id,
                "thread_id": thread_id,
                "content": first_user_message,
                "created_by_user_id": created_by_user_id,
            },
        )
        self.session.flush()
        return ChatThreadIds(thread_id=thread_id, first_message_id=message_id)

    def create_agent_run(
        self,
        *,
        organization_id: str,
        case_id: str,
        thread_id: str | None,
        agent_type: str,
        model: str,
        status: str = "complete",
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
    ) -> str:
        agent_run_id = new_id("agent")
        self.session.execute(
            text(
                """
                INSERT INTO agent_runs (
                    agent_run_id, organization_id, case_id, thread_id, agent_type,
                    status, model, input, output, started_at, completed_at
                )
                VALUES (
                    :agent_run_id, :organization_id, :case_id, :thread_id, :agent_type,
                    :status, :model, CAST(:input AS jsonb), CAST(:output AS jsonb),
                    CASE WHEN :status IN ('running', 'complete', 'failed') THEN now() ELSE NULL END,
                    CASE WHEN :status IN ('complete', 'failed') THEN now() ELSE NULL END
                )
                """
            ),
            {
                "agent_run_id": agent_run_id,
                "organization_id": organization_id,
                "case_id": case_id,
                "thread_id": thread_id,
                "agent_type": agent_type,
                "status": status,
                "model": model,
                "input": _json(input_payload or {}),
                "output": _json(output_payload or {}),
            },
        )
        self.session.flush()
        return agent_run_id

    def update_agent_run_status(
        self,
        *,
        agent_run_id: str,
        status: str,
        output_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.session.execute(
            text(
                """
                UPDATE agent_runs
                SET
                    status = :status,
                    output = COALESCE(CAST(:output AS jsonb), output),
                    error = :error,
                    completed_at = CASE
                        WHEN :status IN ('complete', 'failed') THEN now()
                        ELSE completed_at
                    END
                WHERE agent_run_id = :agent_run_id
                """
            ),
            {
                "agent_run_id": agent_run_id,
                "status": status,
                "output": _json(output_payload) if output_payload is not None else None,
                "error": error,
            },
        )
        self.session.flush()

    def case_context(self, case_id: str) -> CaseContext | None:
        row = self.session.execute(
            text(
                """
                SELECT case_id, organization_id, created_by_user_id
                FROM cases
                WHERE case_id = :case_id
                """
            ),
            {"case_id": case_id},
        ).mappings().first()
        if row is None:
            return None
        return CaseContext(
            case_id=str(row["case_id"]),
            organization_id=str(row["organization_id"]),
            created_by_user_id=str(row["created_by_user_id"]) if row["created_by_user_id"] else None,
        )

    def thread_belongs_to_case(self, *, case_id: str, thread_id: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM chat_threads
                    WHERE case_id = :case_id
                      AND thread_id = :thread_id
                    """
                ),
                {"case_id": case_id, "thread_id": thread_id},
            ).first()
        )

    def message_belongs_to_thread(self, *, thread_id: str, message_id: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM chat_messages
                    WHERE thread_id = :thread_id
                      AND message_id = :message_id
                    """
                ),
                {"thread_id": thread_id, "message_id": message_id},
            ).first()
        )

    def agent_run_belongs_to_case(self, *, case_id: str, agent_run_id: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM agent_runs
                    WHERE case_id = :case_id
                      AND agent_run_id = :agent_run_id
                    """
                ),
                {"case_id": case_id, "agent_run_id": agent_run_id},
            ).first()
        )

    def user_has_case_permission(self, *, case_id: str, user_id: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM case_permissions cp
                    JOIN app_users au ON au.user_id = cp.user_id
                    WHERE cp.case_id = :case_id
                      AND cp.user_id = :user_id
                      AND au.status = 'active'
                    """
                ),
                {"case_id": case_id, "user_id": user_id},
            ).first()
        )

    def user_context(self, user_id: str) -> UserContext | None:
        row = self.session.execute(
            text(
                """
                SELECT user_id, organization_id
                FROM app_users
                WHERE user_id = :user_id
                  AND status = 'active'
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
        if row is None:
            return None
        return UserContext(
            user_id=str(row["user_id"]),
            organization_id=str(row["organization_id"]) if row["organization_id"] else None,
        )

    def case_workspace_snapshot(self, *, case_id: str, user_id: str) -> dict[str, Any]:
        case_context = self.case_context(case_id)
        if case_context is None:
            raise ValueError(f"Case not found: {case_id}")
        organization_id = case_context.organization_id
        projects, cases = self._workspace_navigation(organization_id=organization_id, user_id=user_id)
        return {
            "activeCaseId": case_id,
            "projects": projects,
            "cases": cases,
            "messages": self._workspace_messages(case_id=case_id, limit=200),
            "documents": self._workspace_documents(case_id=case_id, limit=250),
            "researchPackItems": self._workspace_research_pack_items(case_id=case_id, limit=250),
            "drafts": self._workspace_drafts(case_id=case_id, limit=100),
            "reviewItems": self._workspace_review_items(case_id=case_id, limit=100),
        }

    def case_document_file_context(self, *, case_id: str, document_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                WITH case_pack_ids AS (
                    SELECT pack_id
                    FROM case_research_packs
                    WHERE case_id = :case_id
                      AND status = 'active'
                    UNION
                    SELECT pack_id
                    FROM research_packs
                    WHERE case_id = :case_id
                ),
                authorized_documents AS (
                    SELECT
                        COALESCE(cd.document_id, cd.case_document_id) AS document_id,
                        COALESCE(d.title, cd.title) AS title,
                        COALESCE(d.document_type, cd.document_kind, cd.document_role, 'case_document') AS document_type,
                        COALESCE(cd.local_path, d.local_path) AS local_path,
                        COALESCE(cd.source_url, d.source_url) AS source_url,
                        d.download_url AS download_url,
                        COALESCE(cd.file_hash, d.file_hash) AS file_hash
                    FROM case_documents cd
                    LEFT JOIN documents d ON d.document_id = cd.document_id
                    WHERE cd.case_id = :case_id
                      AND cd.status = 'active'
                      AND COALESCE(cd.document_id, cd.case_document_id) = :document_id
                    UNION ALL
                    SELECT DISTINCT
                        d.document_id,
                        d.title,
                        d.document_type,
                        d.local_path,
                        d.source_url,
                        d.download_url,
                        d.file_hash
                    FROM case_pack_ids cpi
                    JOIN research_pack_items rpi ON rpi.pack_id = cpi.pack_id
                    JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                    JOIN documents d ON d.document_id = rc.document_id
                    WHERE d.document_id = :document_id
                )
                SELECT *
                FROM authorized_documents
                LIMIT 1
                """
            ),
            {"case_id": case_id, "document_id": document_id},
        ).mappings().first()
        if row is None:
            return None
        return _case_document_file_context(case_id=case_id, row=row)

    def cache_case_document_file(self, *, case_id: str, document_id: str) -> dict[str, Any] | None:
        context = self.case_document_file_context(case_id=case_id, document_id=document_id)
        if context is None:
            return None
        cached_path = Path(context["case_file_path"])
        if cached_path.is_file():
            return context

        cached_path.parent.mkdir(parents=True, exist_ok=True)
        source_path = Path(context["absolute_local_path"]) if context.get("absolute_local_path") else None
        if source_path is not None and source_path.is_file():
            _copy_case_file(source_path=source_path, cached_path=cached_path)
        else:
            source_url = context.get("download_url") or context.get("source_url")
            if not source_url:
                raise FileNotFoundError("No local file or remote source is available for this case document")
            _download_case_file(source_url=str(source_url), cached_path=cached_path)
        return self.case_document_file_context(case_id=case_id, document_id=document_id)

    def case_workspace_document(self, *, case_id: str, document_id: str) -> dict[str, Any] | None:
        for document in self._workspace_documents(case_id=case_id, limit=1000):
            if document["documentId"] == document_id:
                return document
        return None

    def case_workspace_documents_page(self, *, case_id: str, limit: int, offset: int) -> dict[str, Any]:
        fetch_limit = min(1000, limit + offset + 1)
        documents = self._workspace_documents(case_id=case_id, limit=fetch_limit)
        paged_documents = documents[offset : offset + limit]
        return {
            "caseId": case_id,
            "documents": paged_documents,
            "limit": limit,
            "offset": offset,
            "hasMore": len(documents) > offset + limit,
        }

    def _workspace_navigation(self, *, organization_id: str, user_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        case_rows = self.session.execute(
            text(
                """
                SELECT
                    c.case_id,
                    COALESCE(c.project_id, 'project_uncategorized') AS project_id,
                    c.title,
                    c.court,
                    c.matter_type,
                    GREATEST(
                        c.updated_at,
                        COALESCE(max(ct.updated_at), c.updated_at),
                        COALESCE(max(d.updated_at), c.updated_at),
                        COALESCE(max(ri.updated_at), c.updated_at)
                    ) AS updated_at
                FROM cases c
                JOIN case_permissions cp
                    ON cp.case_id = c.case_id
                   AND cp.user_id = :user_id
                LEFT JOIN chat_threads ct
                    ON ct.case_id = c.case_id
                   AND ct.status = 'active'
                LEFT JOIN drafts d
                    ON d.case_id = c.case_id
                LEFT JOIN review_items ri
                    ON ri.case_id = c.case_id
                WHERE c.organization_id = :organization_id
                  AND c.status = 'active'
                GROUP BY c.case_id, c.project_id, c.title, c.court, c.matter_type, c.updated_at
                ORDER BY updated_at DESC, c.title ASC
                LIMIT 300
                """
            ),
            {"organization_id": organization_id, "user_id": user_id},
        ).mappings().all()
        cases = [
            {
                "caseId": str(row["case_id"]),
                "projectId": str(row["project_id"]),
                "title": str(row["title"]),
                "court": str(row["court"]) if row["court"] else None,
                "matterType": str(row["matter_type"]) if row["matter_type"] else None,
                "updatedAt": row["updated_at"],
            }
            for row in case_rows
        ]

        project_rows = self.session.execute(
            text(
                """
                SELECT
                    p.project_id,
                    p.name,
                    count(DISTINCT c.case_id)::int AS active_case_count
                FROM projects p
                JOIN cases c
                    ON c.project_id = p.project_id
                   AND c.status = 'active'
                JOIN case_permissions cp
                    ON cp.case_id = c.case_id
                   AND cp.user_id = :user_id
                WHERE p.organization_id = :organization_id
                  AND p.status = 'active'
                GROUP BY p.project_id, p.name, p.updated_at
                ORDER BY p.updated_at DESC, p.name ASC
                LIMIT 200
                """
            ),
            {"organization_id": organization_id, "user_id": user_id},
        ).mappings().all()
        projects = [
            {
                "projectId": str(row["project_id"]),
                "name": str(row["name"]),
                "activeCaseCount": int(row["active_case_count"]),
            }
            for row in project_rows
        ]
        if any(case["projectId"] == "project_uncategorized" for case in cases):
            uncategorized_count = sum(1 for case in cases if case["projectId"] == "project_uncategorized")
            projects.append(
                {
                    "projectId": "project_uncategorized",
                    "name": "Uncategorized matters",
                    "activeCaseCount": uncategorized_count,
                }
            )
        return projects, cases

    def _workspace_messages(self, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                SELECT *
                FROM (
                    SELECT
                        cm.message_id,
                        cm.thread_id,
                        cm.role,
                        cm.content,
                        cm.created_at,
                        cm.metadata->>'pack_id' AS pack_id
                    FROM chat_messages cm
                    JOIN chat_threads ct ON ct.thread_id = cm.thread_id
                    WHERE ct.case_id = :case_id
                      AND ct.status = 'active'
                      AND cm.status = 'complete'
                    ORDER BY cm.created_at DESC, cm.message_id DESC
                    LIMIT :limit
                ) recent
                ORDER BY created_at ASC, message_id ASC
                """
            ),
            {"case_id": case_id, "limit": limit},
        ).mappings().all()
        return [
            {
                "messageId": str(row["message_id"]),
                "threadId": str(row["thread_id"]),
                "role": str(row["role"]),
                "content": str(row["content"]),
                "createdAt": row["created_at"],
                "packId": str(row["pack_id"]) if row["pack_id"] else None,
            }
            for row in rows
        ]

    def _workspace_documents(self, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        case_document_rows = self.session.execute(
            text(
                """
                SELECT
                    :case_id AS case_id,
                    COALESCE(cd.document_id, cd.case_document_id) AS document_id,
                    COALESCE(d.title, cd.title) AS title,
                    COALESCE(d.document_type, cd.document_kind, cd.document_role, 'case_document') AS document_type,
                    COALESCE(chunk_summary.citation, cd.title) AS citation,
                    COALESCE(d.source_id, 'case_file') AS source_id,
                    COALESCE(chunk_summary.authority_level, 99) AS authority_level,
                    COALESCE(page_summary.page_count, 0) AS page_count,
                    COALESCE(page_summary.text_preview, chunk_summary.text_preview, cd.metadata->>'summary', '') AS text_preview,
                    COALESCE(cd.local_path, d.local_path) AS local_path,
                    COALESCE(cd.source_url, d.source_url) AS source_url,
                    d.download_url,
                    d.notes AS document_notes,
                    COALESCE(page_summary.quality_flags, '{}'::text[])
                        || COALESCE(chunk_summary.quality_flags, '{}'::text[]) AS quality_flags,
                    relevance_summary.relevance_score,
                    relevance_summary.confidence_score,
                    relevance_summary.relevance_band,
                    relevance_summary.rationale AS relevance_rationale,
                    cd.created_at
                FROM case_documents cd
                LEFT JOIN documents d ON d.document_id = cd.document_id
                LEFT JOIN LATERAL (
                    SELECT
                        (
                            SELECT count(*)::int
                            FROM pages all_pages
                            WHERE all_pages.document_id = d.document_id
                        ) AS page_count,
                        (
                            SELECT left(string_agg(NULLIF(preview_pages.text, ''), E'\n\n' ORDER BY preview_pages.page_number), 1600)
                            FROM (
                                SELECT page_number, text
                                FROM pages
                                WHERE document_id = d.document_id
                                  AND NULLIF(text, '') IS NOT NULL
                                ORDER BY page_number
                                LIMIT 8
                            ) preview_pages
                        ) AS text_preview,
                        COALESCE(
                            ARRAY(
                                SELECT DISTINCT page_flag.flag
                                FROM (
                                    SELECT quality_flags
                                    FROM pages
                                    WHERE document_id = d.document_id
                                    ORDER BY page_number
                                    LIMIT 8
                                ) preview_pages
                                LEFT JOIN LATERAL unnest(preview_pages.quality_flags) AS page_flag(flag) ON true
                                WHERE page_flag.flag IS NOT NULL
                            ),
                            '{}'::text[]
                        ) AS quality_flags
                ) page_summary ON true
                LEFT JOIN LATERAL (
                    SELECT
                        (
                            SELECT min(citation)
                            FROM retrieval_chunks all_chunks
                            WHERE all_chunks.document_id = d.document_id
                        ) AS citation,
                        (
                            SELECT min(authority_level)::int
                            FROM retrieval_chunks all_chunks
                            WHERE all_chunks.document_id = d.document_id
                        ) AS authority_level,
                        (
                            SELECT left(string_agg(NULLIF(preview_chunks.chunk_text, ''), E'\n\n' ORDER BY preview_chunks.chunk_index), 1600)
                            FROM (
                                SELECT chunk_index, chunk_text
                                FROM retrieval_chunks
                                WHERE document_id = d.document_id
                                  AND NULLIF(chunk_text, '') IS NOT NULL
                                ORDER BY chunk_index
                                LIMIT 16
                            ) preview_chunks
                        ) AS text_preview,
                        COALESCE(
                            ARRAY(
                                SELECT DISTINCT chunk_flag.flag
                                FROM (
                                    SELECT quality_flags
                                    FROM retrieval_chunks
                                    WHERE document_id = d.document_id
                                    ORDER BY chunk_index
                                    LIMIT 16
                                ) preview_chunks
                                LEFT JOIN LATERAL unnest(preview_chunks.quality_flags) AS chunk_flag(flag) ON true
                                WHERE chunk_flag.flag IS NOT NULL
                            ),
                            '{}'::text[]
                        ) AS quality_flags
                ) chunk_summary ON true
                LEFT JOIN LATERAL (
                    SELECT
                        cdr.relevance_score,
                        cdr.confidence_score,
                        cdr.relevance_band,
                        cdr.rationale
                    FROM case_document_relevance cdr
                    WHERE cdr.case_id = :case_id
                      AND cdr.status IN ('candidate', 'included', 'reviewed')
                      AND (
                        (cdr.case_document_id IS NOT NULL AND cdr.case_document_id = cd.case_document_id)
                        OR (cdr.document_id IS NOT NULL AND cdr.document_id = d.document_id)
                      )
                    ORDER BY cdr.relevance_score DESC, cdr.created_at DESC
                    LIMIT 1
                ) relevance_summary ON true
                WHERE cd.case_id = :case_id
                  AND cd.status = 'active'
                ORDER BY cd.created_at DESC, cd.title ASC
                LIMIT :limit
                """
            ),
            {"case_id": case_id, "limit": limit},
        ).mappings().all()

        documents: dict[str, dict[str, Any]] = {}
        for row in case_document_rows:
            document = _workspace_document(row)
            documents[document["documentId"]] = document

        cited_rows = self.session.execute(
            text(
                """
                WITH case_pack_ids AS (
                    SELECT pack_id
                    FROM case_research_packs
                    WHERE case_id = :case_id
                      AND status = 'active'
                    UNION
                    SELECT pack_id
                    FROM research_packs
                    WHERE case_id = :case_id
                )
                SELECT
                    :case_id AS case_id,
                    rc.document_id,
                    max(rc.title) AS title,
                    max(rc.document_type) AS document_type,
                    min(rc.citation) AS citation,
                    max(rc.source_id) AS source_id,
                    min(rc.authority_level)::int AS authority_level,
                    COALESCE(page_summary.page_count, 0)::int AS page_count,
                    COALESCE(
                        page_summary.text_preview,
                        left(
                            string_agg(DISTINCT rc.chunk_text, E'\n\n')
                                FILTER (WHERE NULLIF(rc.chunk_text, '') IS NOT NULL),
                            1600
                        ),
                        ''
                    ) AS text_preview,
                    d.local_path,
                    d.source_url,
                    d.download_url,
                    d.notes AS document_notes,
                    COALESCE(page_summary.quality_flags, '{}'::text[])
                        || COALESCE(array_agg(DISTINCT chunk_flag.flag) FILTER (WHERE chunk_flag.flag IS NOT NULL), '{}'::text[]) AS quality_flags,
                    max(cdr.relevance_score) AS relevance_score,
                    max(cdr.confidence_score) AS confidence_score,
                    (array_agg(cdr.relevance_band ORDER BY cdr.relevance_score DESC NULLS LAST))[1] AS relevance_band,
                    (array_agg(cdr.rationale ORDER BY cdr.relevance_score DESC NULLS LAST))[1] AS relevance_rationale,
                    max(rp.created_at) AS created_at
                FROM case_pack_ids cpi
                JOIN research_packs rp ON rp.pack_id = cpi.pack_id
                JOIN research_pack_items rpi ON rpi.pack_id = cpi.pack_id
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                JOIN documents d ON d.document_id = rc.document_id
                LEFT JOIN LATERAL (
                    SELECT
                        (
                            SELECT count(*)::int
                            FROM pages all_pages
                            WHERE all_pages.document_id = d.document_id
                        ) AS page_count,
                        (
                            SELECT left(string_agg(NULLIF(preview_pages.text, ''), E'\n\n' ORDER BY preview_pages.page_number), 1600)
                            FROM (
                                SELECT page_number, text
                                FROM pages
                                WHERE document_id = d.document_id
                                  AND NULLIF(text, '') IS NOT NULL
                                ORDER BY page_number
                                LIMIT 8
                            ) preview_pages
                        ) AS text_preview,
                        COALESCE(
                            ARRAY(
                                SELECT DISTINCT page_flag.flag
                                FROM (
                                    SELECT quality_flags
                                    FROM pages
                                    WHERE document_id = d.document_id
                                    ORDER BY page_number
                                    LIMIT 8
                                ) preview_pages
                                LEFT JOIN LATERAL unnest(preview_pages.quality_flags) AS page_flag(flag) ON true
                                WHERE page_flag.flag IS NOT NULL
                            ),
                            '{}'::text[]
                        ) AS quality_flags
                ) page_summary ON true
                LEFT JOIN LATERAL unnest(rc.quality_flags) AS chunk_flag(flag) ON true
                LEFT JOIN case_document_relevance cdr
                    ON cdr.case_id = :case_id
                   AND cdr.document_id = d.document_id
                   AND cdr.status IN ('candidate', 'included', 'reviewed')
                GROUP BY
                    rc.document_id, d.local_path, d.source_url, d.download_url,
                    d.notes, page_summary.page_count, page_summary.text_preview,
                    page_summary.quality_flags
                ORDER BY max(rp.created_at) DESC, min(rpi.rank) ASC
                LIMIT :limit
                """
            ),
            {"case_id": case_id, "limit": limit},
        ).mappings().all()
        for row in cited_rows:
            document = _workspace_document(row)
            existing = documents.get(document["documentId"])
            if existing is None:
                documents[document["documentId"]] = document
            else:
                existing["qualityFlags"] = _dedupe(existing["qualityFlags"] + document["qualityFlags"])
                if not existing["textPreview"]:
                    existing["textPreview"] = document["textPreview"]
                if existing["citation"] == existing["title"]:
                    existing["citation"] = document["citation"]
                if (existing.get("relevanceScore") or 0) < (document.get("relevanceScore") or 0):
                    existing["relevanceScore"] = document.get("relevanceScore")
                    existing["confidenceScore"] = document.get("confidenceScore")
                    existing["relevanceBand"] = document.get("relevanceBand")
                    existing["relevanceRationale"] = document.get("relevanceRationale")
        return list(documents.values())[:limit]

    def _workspace_research_pack_items(self, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                WITH case_pack_ids AS (
                    SELECT pack_id
                    FROM case_research_packs
                    WHERE case_id = :case_id
                      AND status = 'active'
                    UNION
                    SELECT pack_id
                    FROM research_packs
                    WHERE case_id = :case_id
                )
                SELECT
                    rpi.pack_item_id,
                    rpi.pack_id,
                    rc.document_id,
                    rc.citation,
                    rc.title,
                    rc.authority_level,
                    rpi.fused_score,
                    rpi.selection_reason,
                    COALESCE(rpi.source_quality_flags, '{}'::text[])
                        || COALESCE(rp.source_warnings, '{}'::text[]) AS source_warnings
                FROM case_pack_ids cpi
                JOIN research_packs rp ON rp.pack_id = cpi.pack_id
                JOIN research_pack_items rpi ON rpi.pack_id = cpi.pack_id
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                ORDER BY rp.created_at DESC, rpi.rank ASC, rpi.pack_item_id ASC
                LIMIT :limit
                """
            ),
            {"case_id": case_id, "limit": limit},
        ).mappings().all()
        pack_item_ids = [str(row["pack_item_id"]) for row in rows]
        anchors_by_item = self._workspace_source_anchors(pack_item_ids)
        return [
            {
                "packItemId": str(row["pack_item_id"]),
                "packId": str(row["pack_id"]),
                "documentId": str(row["document_id"]),
                "citation": str(row["citation"]),
                "title": str(row["title"]),
                "authorityLevel": int(row["authority_level"]),
                "fusedScore": float(row["fused_score"]),
                "selectionReason": str(row["selection_reason"]),
                "sourceWarnings": _dedupe(_text_list(row["source_warnings"])),
                "anchors": anchors_by_item.get(str(row["pack_item_id"]), []),
            }
            for row in rows
        ]

    def _workspace_source_anchors(self, pack_item_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not pack_item_ids:
            return {}
        rows = self.session.execute(
            text(
                """
                SELECT
                    pack_item_id,
                    anchor_id,
                    page_number,
                    quote,
                    confidence
                FROM pack_item_source_anchors
                WHERE pack_item_id = ANY(:pack_item_ids)
                  AND status = 'active'
                ORDER BY pack_item_id ASC, anchor_index ASC
                """
            ),
            {"pack_item_ids": pack_item_ids},
        ).mappings().all()
        anchors: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            pack_item_id = str(row["pack_item_id"])
            anchors.setdefault(pack_item_id, []).append(
                {
                    "anchorId": str(row["anchor_id"]),
                    "pageNumber": int(row["page_number"]) if row["page_number"] is not None else None,
                    "quote": str(row["quote"]),
                    "confidence": float(row["confidence"]),
                }
            )
        return anchors

    def _workspace_drafts(self, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        drafts: list[dict[str, Any]] = []
        for row in self.list_case_drafts(case_id=case_id, limit=limit):
            metadata = dict(row.get("metadata") or {})
            drafts.append(
                {
                    "draftId": str(row["draft_id"]),
                    "title": str(row["title"]),
                    "draftType": str(row["draft_type"]),
                    "requestedOutput": str(metadata["requested_output"]) if metadata.get("requested_output") else None,
                    "status": str(row["status"]),
                    "reviewStatus": str(row["review_status"]) if row["review_status"] else None,
                    "contentPreview": str(row["content_preview"] or ""),
                    "claimCount": int(row["claim_count"]),
                    "reasoningPack": metadata.get("reasoning_pack"),
                }
            )
        return drafts

    def _workspace_review_items(self, *, case_id: str, limit: int) -> list[dict[str, Any]]:
        return [
            {
                "reviewItemId": str(row["review_item_id"]),
                "itemType": str(row["item_type"]),
                "itemTitle": str(row["item_title"]),
                "status": str(row["status"]),
                "priority": str(row["priority"]),
            }
            for row in self.list_review_items(case_id=case_id, status=None, limit=limit)
        ]

    def user_has_organization_audit_access(self, *, organization_id: str, user_id: str) -> bool:
        return bool(
            self.session.execute(
                text(
                    """
                    SELECT 1
                    FROM app_users au
                    LEFT JOIN organization_memberships om
                        ON om.user_id = au.user_id
                       AND om.organization_id = :organization_id
                       AND om.status = 'active'
                    WHERE au.user_id = :user_id
                      AND au.status = 'active'
                      AND (
                          au.organization_id = :organization_id
                          OR om.organization_id = :organization_id
                      )
                      AND (
                          au.role IN ('owner', 'admin', 'super_admin', 'organization_admin')
                          OR om.role IN ('owner', 'admin', 'organization_admin')
                      )
                    """
                ),
                {"organization_id": organization_id, "user_id": user_id},
            ).first()
        )

    def consume_rate_limit(
        self,
        *,
        organization_id: str | None,
        user_id: str,
        route_key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        if limit < 1:
            raise ValueError("rate limit must be at least 1")
        if window_seconds < 1:
            raise ValueError("rate limit window must be at least 1 second")
        row = self.session.execute(
            text(
                """
                WITH rate_window AS (
                    SELECT to_timestamp(
                        floor(extract(epoch FROM now()) / :window_seconds) * :window_seconds
                    ) AS window_started_at
                ),
                upserted AS (
                    INSERT INTO api_rate_limits (
                        organization_id, user_id, route_key, window_started_at,
                        window_seconds, request_count, last_request_at
                    )
                    SELECT
                        :organization_id, :user_id, :route_key, window_started_at,
                        :window_seconds, 1, now()
                    FROM rate_window
                    ON CONFLICT (user_id, route_key, window_started_at)
                    DO UPDATE SET
                        organization_id = COALESCE(EXCLUDED.organization_id, api_rate_limits.organization_id),
                        window_seconds = EXCLUDED.window_seconds,
                        request_count = api_rate_limits.request_count + 1,
                        last_request_at = now()
                    RETURNING request_count, window_started_at, window_seconds
                )
                SELECT
                    request_count,
                    window_started_at,
                    window_started_at + (:window_seconds * INTERVAL '1 second') AS resets_at,
                    GREATEST(
                        1,
                        CEIL(
                            EXTRACT(EPOCH FROM (
                                (window_started_at + (:window_seconds * INTERVAL '1 second')) - now()
                            ))
                        )::int
                    ) AS retry_after_seconds
                FROM upserted
                """
            ),
            {
                "organization_id": organization_id,
                "user_id": user_id,
                "route_key": route_key,
                "window_seconds": window_seconds,
            },
        ).mappings().one()
        self.session.flush()
        return RateLimitResult(
            route_key=route_key,
            request_count=int(row["request_count"]),
            limit=limit,
            window_seconds=window_seconds,
            window_started_at=row["window_started_at"],
            resets_at=row["resets_at"],
            retry_after_seconds=int(row["retry_after_seconds"]),
        )

    def prune_expired_rate_limits(self, *, retention_seconds: int) -> RateLimitPruneResult:
        if retention_seconds < 1:
            raise ValueError("rate limit retention must be at least 1 second")
        row = self.session.execute(
            text(
                """
                WITH cutoff_value AS (
                    SELECT now() - (:retention_seconds * INTERVAL '1 second') AS cutoff
                ),
                deleted AS (
                    DELETE FROM api_rate_limits
                    WHERE last_request_at < (SELECT cutoff FROM cutoff_value)
                    RETURNING 1
                )
                SELECT
                    (SELECT cutoff FROM cutoff_value) AS cutoff,
                    count(*) AS deleted_count
                FROM deleted
                """
            ),
            {"retention_seconds": retention_seconds},
        ).mappings().one()
        self.session.flush()
        return RateLimitPruneResult(
            retention_seconds=retention_seconds,
            cutoff=row["cutoff"],
            deleted_count=int(row["deleted_count"]),
        )

    def rebuild_daily_operational_rollups(self, *, rollup_date: date) -> OperationalRollupResult:
        self.session.execute(
            text(
                """
                DELETE FROM operational_metric_rollups
                WHERE rollup_date = :rollup_date
                  AND source IN ('audit_events', 'api_rate_limits')
                """
            ),
            {"rollup_date": rollup_date},
        )
        audit_rows = self.session.execute(
            text(
                """
                WITH daily AS (
                    SELECT
                        event_type,
                        COALESCE(entity_id, 'unknown') AS route_key,
                        count(*)::numeric AS metric_value
                    FROM audit_events
                    WHERE created_at >= CAST(:rollup_date AS date)
                      AND created_at < CAST(:rollup_date AS date) + INTERVAL '1 day'
                      AND event_type IN ('api.rate_limit.exceeded', 'api.request_body.too_large')
                    GROUP BY event_type, COALESCE(entity_id, 'unknown')
                )
                SELECT
                    CASE
                        WHEN event_type = 'api.rate_limit.exceeded'
                            THEN 'guardrail_rate_limit_rejections_total'
                        WHEN event_type = 'api.request_body.too_large'
                            THEN 'guardrail_request_body_too_large_total'
                    END AS metric_name,
                    jsonb_build_object('event_type', event_type, 'route_key', route_key) AS labels,
                    metric_value
                FROM daily
                """
            ),
            {"rollup_date": rollup_date},
        ).mappings().all()
        rate_limit_rows = self.session.execute(
            text(
                """
                SELECT
                    'rate_limit_window_requests_total' AS metric_name,
                    jsonb_build_object('route_key', route_key) AS labels,
                    sum(request_count)::numeric AS metric_value
                FROM api_rate_limits
                WHERE window_started_at >= CAST(:rollup_date AS date)
                  AND window_started_at < CAST(:rollup_date AS date) + INTERVAL '1 day'
                GROUP BY route_key
                """
            ),
            {"rollup_date": rollup_date},
        ).mappings().all()
        upserted_count = 0
        for row in audit_rows:
            self.upsert_operational_metric_rollup(
                rollup_date=rollup_date,
                metric_name=str(row["metric_name"]),
                source="audit_events",
                labels=dict(row["labels"]),
                metric_value=row["metric_value"],
            )
            upserted_count += 1
        for row in rate_limit_rows:
            self.upsert_operational_metric_rollup(
                rollup_date=rollup_date,
                metric_name=str(row["metric_name"]),
                source="api_rate_limits",
                labels=dict(row["labels"]),
                metric_value=row["metric_value"],
            )
            upserted_count += 1
        self.session.flush()
        return OperationalRollupResult(
            rollup_date=rollup_date,
            source="audit_events,api_rate_limits",
            upserted_count=upserted_count,
        )

    def upsert_operational_metric_rollup(
        self,
        *,
        rollup_date: date,
        metric_name: str,
        source: str,
        labels: dict[str, Any],
        metric_value: int | float | str,
    ) -> None:
        label_hash = _sha256(_json(_sorted_dict(labels)))
        self.session.execute(
            text(
                """
                INSERT INTO operational_metric_rollups (
                    rollup_date, metric_name, source, label_hash, labels, metric_value, computed_at
                )
                VALUES (
                    :rollup_date, :metric_name, :source, :label_hash,
                    CAST(:labels AS jsonb), :metric_value, now()
                )
                ON CONFLICT (rollup_date, metric_name, source, label_hash)
                DO UPDATE SET
                    labels = EXCLUDED.labels,
                    metric_value = EXCLUDED.metric_value,
                    computed_at = now()
                """
            ),
            {
                "rollup_date": rollup_date,
                "metric_name": metric_name,
                "source": source,
                "label_hash": label_hash,
                "labels": _json(_sorted_dict(labels)),
                "metric_value": metric_value,
            },
        )
        self.session.flush()

    def list_operational_metric_rollups(
        self,
        *,
        rollup_date: date,
        metric_name: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = ["rollup_date = :rollup_date"]
        params: dict[str, Any] = {"rollup_date": rollup_date}
        if metric_name is not None:
            conditions.append("metric_name = :metric_name")
            params["metric_name"] = metric_name
        if source is not None:
            conditions.append("source = :source")
            params["source"] = source
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    rollup_date,
                    metric_name,
                    source,
                    labels,
                    metric_value,
                    computed_at
                FROM operational_metric_rollups
                WHERE {' AND '.join(conditions)}
                ORDER BY metric_name, source, labels::text
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "rollup_date": row["rollup_date"],
                "metric_name": str(row["metric_name"]),
                "source": str(row["source"]),
                "labels": dict(row["labels"]),
                "metric_value": int(row["metric_value"]) if row["metric_value"] == int(row["metric_value"]) else float(row["metric_value"]),
                "computed_at": row["computed_at"],
            }
            for row in rows
        ]

    def start_ingestion_run(
        self,
        *,
        source_id: str,
        pipeline_name: str,
        pipeline_version: str,
        manifest_path: str | None = None,
        corpus_root: str | None = None,
        input_manifest_hash: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        ingestion_run_id = new_id("ingest")
        self.session.execute(
            text(
                """
                INSERT INTO ingestion_runs (
                    ingestion_run_id, source_id, pipeline_name, pipeline_version,
                    status, manifest_path, corpus_root, input_manifest_hash, config
                )
                VALUES (
                    :ingestion_run_id, :source_id, :pipeline_name, :pipeline_version,
                    'running', :manifest_path, :corpus_root, :input_manifest_hash,
                    CAST(:config AS jsonb)
                )
                """
            ),
            {
                "ingestion_run_id": ingestion_run_id,
                "source_id": source_id,
                "pipeline_name": pipeline_name,
                "pipeline_version": pipeline_version,
                "manifest_path": manifest_path,
                "corpus_root": corpus_root,
                "input_manifest_hash": input_manifest_hash,
                "config": _json(config or {}),
            },
        )
        self.session.flush()
        return ingestion_run_id

    def record_document_ingestion_event(
        self,
        *,
        ingestion_run_id: str,
        document_id: str,
        source_id: str,
        document_type: str,
        title: str,
        stage: str,
        status: str,
        source_document_id: str | None = None,
        year: int | None = None,
        number: str | None = None,
        document_date: date | None = None,
        language: str | None = None,
        source_url: str | None = None,
        download_url: str | None = None,
        local_path: str | None = None,
        file_hash: str | None = None,
        acquisition_status: str = "downloaded",
        extraction_status: str = "pending",
        extraction_method: str | None = None,
        ocr_required: bool | None = None,
        ocr_engine: str | None = None,
        page_count: int = 0,
        chunk_count: int = 0,
        text_hash: str | None = None,
        text_quality_score: float | None = None,
        quality_flags: list[str] | None = None,
        legal_status: str | None = None,
        missing_reason: str | None = None,
        next_action: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        notes: str | None = None,
        metadata: dict[str, Any] | None = None,
        version_label: str | None = None,
        source_snapshot: dict[str, Any] | None = None,
    ) -> DocumentIngestionEventResult:
        if page_count < 0:
            raise ValueError("page_count cannot be negative")
        if chunk_count < 0:
            raise ValueError("chunk_count cannot be negative")

        current_quality_flags = quality_flags or []
        self.session.execute(
            text(
                """
                INSERT INTO documents (
                    document_id, source_id, source_document_id, document_type, title,
                    year, number, document_date, language, source_url, download_url,
                    local_path, file_hash, acquisition_status, extraction_status,
                    ocr_required, text_quality_score, legal_status, missing_reason,
                    next_action, notes, current_ingestion_run_id, last_ingested_at,
                    last_checked
                )
                VALUES (
                    :document_id, :source_id, :source_document_id, :document_type, :title,
                    :year, :number, :document_date, :language, :source_url, :download_url,
                    :local_path, :file_hash, :acquisition_status, :extraction_status,
                    :ocr_required, :text_quality_score, :legal_status, :missing_reason,
                    :next_action, :notes, :ingestion_run_id, now(), now()
                )
                ON CONFLICT (document_id) DO UPDATE SET
                    source_id = EXCLUDED.source_id,
                    source_document_id = COALESCE(EXCLUDED.source_document_id, documents.source_document_id),
                    document_type = EXCLUDED.document_type,
                    title = EXCLUDED.title,
                    year = COALESCE(EXCLUDED.year, documents.year),
                    number = COALESCE(EXCLUDED.number, documents.number),
                    document_date = COALESCE(EXCLUDED.document_date, documents.document_date),
                    language = COALESCE(EXCLUDED.language, documents.language),
                    source_url = COALESCE(EXCLUDED.source_url, documents.source_url),
                    download_url = COALESCE(EXCLUDED.download_url, documents.download_url),
                    local_path = COALESCE(EXCLUDED.local_path, documents.local_path),
                    file_hash = COALESCE(EXCLUDED.file_hash, documents.file_hash),
                    acquisition_status = EXCLUDED.acquisition_status,
                    extraction_status = EXCLUDED.extraction_status,
                    ocr_required = COALESCE(EXCLUDED.ocr_required, documents.ocr_required),
                    text_quality_score = COALESCE(EXCLUDED.text_quality_score, documents.text_quality_score),
                    legal_status = COALESCE(EXCLUDED.legal_status, documents.legal_status),
                    missing_reason = EXCLUDED.missing_reason,
                    next_action = EXCLUDED.next_action,
                    notes = COALESCE(EXCLUDED.notes, documents.notes),
                    current_ingestion_run_id = EXCLUDED.current_ingestion_run_id,
                    last_ingested_at = now(),
                    last_checked = now(),
                    updated_at = now()
                """
            ),
            {
                "document_id": document_id,
                "source_id": source_id,
                "source_document_id": source_document_id,
                "document_type": document_type,
                "title": title,
                "year": year,
                "number": number,
                "document_date": document_date,
                "language": language,
                "source_url": source_url,
                "download_url": download_url,
                "local_path": local_path,
                "file_hash": file_hash,
                "acquisition_status": acquisition_status,
                "extraction_status": extraction_status,
                "ocr_required": ocr_required,
                "text_quality_score": text_quality_score,
                "legal_status": legal_status,
                "missing_reason": missing_reason,
                "next_action": next_action,
                "notes": notes,
                "ingestion_run_id": ingestion_run_id,
            },
        )
        event_row = self.session.execute(
            text(
                """
                INSERT INTO document_ingestion_events (
                    ingestion_run_id, document_id, source_id, source_document_id,
                    local_path, file_hash, stage, status, extraction_method,
                    ocr_required, ocr_engine, page_count, chunk_count, text_hash,
                    text_quality_score, quality_flags, error_code, error_message,
                    metadata
                )
                VALUES (
                    :ingestion_run_id, :document_id, :source_id, :source_document_id,
                    :local_path, :file_hash, :stage, :status, :extraction_method,
                    :ocr_required, :ocr_engine, :page_count, :chunk_count, :text_hash,
                    :text_quality_score, :quality_flags, :error_code, :error_message,
                    CAST(:metadata AS jsonb)
                )
                RETURNING ingestion_event_id
                """
            ),
            {
                "ingestion_run_id": ingestion_run_id,
                "document_id": document_id,
                "source_id": source_id,
                "source_document_id": source_document_id,
                "local_path": local_path,
                "file_hash": file_hash,
                "stage": stage,
                "status": status,
                "extraction_method": extraction_method,
                "ocr_required": ocr_required,
                "ocr_engine": ocr_engine,
                "page_count": page_count,
                "chunk_count": chunk_count,
                "text_hash": text_hash,
                "text_quality_score": text_quality_score,
                "quality_flags": current_quality_flags,
                "error_code": error_code,
                "error_message": error_message,
                "metadata": _json(metadata or {}),
            },
        ).mappings().one()
        if version_label:
            self.session.execute(
                text(
                    """
                    INSERT INTO document_versions (
                        document_id, version_label, file_hash, text_hash,
                        extraction_method, ocr_confidence_band, source_snapshot,
                        ingestion_run_id, page_count, chunk_count, quality_flags
                    )
                    VALUES (
                        :document_id, :version_label, :file_hash, :text_hash,
                        :extraction_method, :ocr_confidence_band,
                        CAST(:source_snapshot AS jsonb), :ingestion_run_id,
                        :page_count, :chunk_count, :quality_flags
                    )
                    ON CONFLICT (document_id, version_label) DO UPDATE SET
                        file_hash = EXCLUDED.file_hash,
                        text_hash = EXCLUDED.text_hash,
                        extraction_method = EXCLUDED.extraction_method,
                        ocr_confidence_band = EXCLUDED.ocr_confidence_band,
                        source_snapshot = EXCLUDED.source_snapshot,
                        ingestion_run_id = EXCLUDED.ingestion_run_id,
                        page_count = EXCLUDED.page_count,
                        chunk_count = EXCLUDED.chunk_count,
                        quality_flags = EXCLUDED.quality_flags
                    """
                ),
                {
                    "document_id": document_id,
                    "version_label": version_label,
                    "file_hash": file_hash,
                    "text_hash": text_hash,
                    "extraction_method": extraction_method,
                    "ocr_confidence_band": _ocr_confidence_band(text_quality_score),
                    "source_snapshot": _json(source_snapshot or {}),
                    "ingestion_run_id": ingestion_run_id,
                    "page_count": page_count,
                    "chunk_count": chunk_count,
                    "quality_flags": current_quality_flags,
                },
            )
        self.session.flush()
        return DocumentIngestionEventResult(
            ingestion_event_id=int(event_row["ingestion_event_id"]),
            document_id=document_id,
            status=status,
            stage=stage,
        )

    def finish_ingestion_run(
        self,
        *,
        ingestion_run_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> IngestionRunSummary:
        if status not in {"complete", "failed", "cancelled"}:
            raise ValueError("finished ingestion run status must be complete, failed, or cancelled")
        row = self.session.execute(
            text(
                """
                WITH event_counts AS (
                    SELECT
                        count(DISTINCT document_id) FILTER (WHERE document_id IS NOT NULL)::int AS document_count,
                        COALESCE(sum(page_count), 0)::int AS page_count,
                        COALESCE(sum(chunk_count), 0)::int AS chunk_count,
                        count(*) FILTER (WHERE status = 'failed')::int AS error_count
                    FROM document_ingestion_events
                    WHERE ingestion_run_id = :ingestion_run_id
                ),
                updated AS (
                    UPDATE ingestion_runs AS ir
                    SET
                        status = :status,
                        output = COALESCE(CAST(:output AS jsonb), ir.output),
                        error = :error,
                        document_count = event_counts.document_count,
                        page_count = event_counts.page_count,
                        chunk_count = event_counts.chunk_count,
                        error_count = event_counts.error_count,
                        completed_at = now(),
                        updated_at = now()
                    FROM event_counts
                    WHERE ir.ingestion_run_id = :ingestion_run_id
                    RETURNING
                        ir.ingestion_run_id, ir.status, ir.document_count,
                        ir.page_count, ir.chunk_count, ir.error_count
                )
                SELECT *
                FROM updated
                """
            ),
            {
                "ingestion_run_id": ingestion_run_id,
                "status": status,
                "output": _json(output) if output is not None else None,
                "error": error,
            },
        ).mappings().one()
        self.session.flush()
        return IngestionRunSummary(
            ingestion_run_id=str(row["ingestion_run_id"]),
            status=str(row["status"]),
            document_count=int(row["document_count"]),
            page_count=int(row["page_count"]),
            chunk_count=int(row["chunk_count"]),
            error_count=int(row["error_count"]),
        )

    def get_ingestion_run(self, ingestion_run_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    ingestion_run_id, source_id, pipeline_name, pipeline_version,
                    status, manifest_path, corpus_root, input_manifest_hash,
                    config, output, error, document_count, page_count,
                    chunk_count, error_count, started_at, completed_at
                FROM ingestion_runs
                WHERE ingestion_run_id = :ingestion_run_id
                """
            ),
            {"ingestion_run_id": ingestion_run_id},
        ).mappings().first()
        return dict(row) if row else None

    def list_document_ingestion_events(
        self,
        *,
        ingestion_run_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        conditions = ["ingestion_run_id = :ingestion_run_id"]
        params: dict[str, Any] = {"ingestion_run_id": ingestion_run_id, "limit": limit}
        if status is not None:
            conditions.append("status = :status")
            params["status"] = status
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    ingestion_event_id, ingestion_run_id, document_id, source_id,
                    source_document_id, local_path, file_hash, stage, status,
                    extraction_method, ocr_required, ocr_engine, page_count,
                    chunk_count, text_hash, text_quality_score, quality_flags,
                    error_code, error_message, metadata, created_at
                FROM document_ingestion_events
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at ASC, ingestion_event_id ASC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        return [
            {
                "ingestion_event_id": int(row["ingestion_event_id"]),
                "ingestion_run_id": str(row["ingestion_run_id"]),
                "document_id": str(row["document_id"]) if row["document_id"] else None,
                "source_id": str(row["source_id"]),
                "source_document_id": str(row["source_document_id"]) if row["source_document_id"] else None,
                "local_path": str(row["local_path"]) if row["local_path"] else None,
                "file_hash": str(row["file_hash"]) if row["file_hash"] else None,
                "stage": str(row["stage"]),
                "status": str(row["status"]),
                "extraction_method": str(row["extraction_method"]) if row["extraction_method"] else None,
                "ocr_required": bool(row["ocr_required"]) if row["ocr_required"] is not None else None,
                "ocr_engine": str(row["ocr_engine"]) if row["ocr_engine"] else None,
                "page_count": int(row["page_count"]),
                "chunk_count": int(row["chunk_count"]),
                "text_hash": str(row["text_hash"]) if row["text_hash"] else None,
                "text_quality_score": float(row["text_quality_score"]) if row["text_quality_score"] is not None else None,
                "quality_flags": list(row["quality_flags"] or []),
                "error_code": str(row["error_code"]) if row["error_code"] else None,
                "error_message": str(row["error_message"]) if row["error_message"] else None,
                "metadata": dict(row["metadata"] or {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def upsert_missing_source_record(
        self,
        *,
        category: str,
        title: str,
        reason: str,
        next_action: str,
        external_missing_id: str | None = None,
        document_id: str | None = None,
        source_id: str | None = None,
        year: int | None = None,
        priority: str = "normal",
        status: str = "open",
        expected_coverage: str | None = None,
        known_available_coverage: str | None = None,
        legal_importance: str | None = None,
        risk_if_missing: str | None = None,
        probable_source: str | None = None,
        owner: str | None = None,
        last_checked: datetime | None = None,
        notes: str | None = None,
    ) -> int:
        row = self.session.execute(
            text(
                """
                INSERT INTO missing_sources (
                    external_missing_id, document_id, source_id, category, title,
                    year, reason, next_action, priority, status, expected_coverage,
                    known_available_coverage, legal_importance, risk_if_missing,
                    probable_source, owner, last_checked, notes, updated_at
                )
                VALUES (
                    :external_missing_id, :document_id, :source_id, :category, :title,
                    :year, :reason, :next_action, :priority, :status, :expected_coverage,
                    :known_available_coverage, :legal_importance, :risk_if_missing,
                    :probable_source, :owner, :last_checked, :notes, now()
                )
                ON CONFLICT (external_missing_id) WHERE external_missing_id IS NOT NULL
                DO UPDATE SET
                    document_id = EXCLUDED.document_id,
                    source_id = EXCLUDED.source_id,
                    category = EXCLUDED.category,
                    title = EXCLUDED.title,
                    year = EXCLUDED.year,
                    reason = EXCLUDED.reason,
                    next_action = EXCLUDED.next_action,
                    priority = EXCLUDED.priority,
                    status = EXCLUDED.status,
                    expected_coverage = EXCLUDED.expected_coverage,
                    known_available_coverage = EXCLUDED.known_available_coverage,
                    legal_importance = EXCLUDED.legal_importance,
                    risk_if_missing = EXCLUDED.risk_if_missing,
                    probable_source = EXCLUDED.probable_source,
                    owner = EXCLUDED.owner,
                    last_checked = EXCLUDED.last_checked,
                    notes = EXCLUDED.notes,
                    updated_at = now()
                RETURNING missing_source_id
                """
            ),
            {
                "external_missing_id": external_missing_id,
                "document_id": document_id,
                "source_id": source_id,
                "category": category,
                "title": title,
                "year": year,
                "reason": reason,
                "next_action": next_action,
                "priority": priority,
                "status": status,
                "expected_coverage": expected_coverage,
                "known_available_coverage": known_available_coverage,
                "legal_importance": legal_importance,
                "risk_if_missing": risk_if_missing,
                "probable_source": probable_source,
                "owner": owner,
                "last_checked": last_checked,
                "notes": notes,
            },
        ).mappings().one()
        self.session.flush()
        return int(row["missing_source_id"])

    def add_chat_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        created_by_user_id: str | None = None,
        parent_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        message_id = new_id("msg")
        self.session.execute(
            text(
                """
                INSERT INTO chat_messages (
                    message_id, thread_id, parent_message_id, role, content,
                    created_by_user_id, metadata
                )
                VALUES (
                    :message_id, :thread_id, :parent_message_id, :role, :content,
                    :created_by_user_id, CAST(:metadata AS jsonb)
                )
                """
            ),
            {
                "message_id": message_id,
                "thread_id": thread_id,
                "parent_message_id": parent_message_id,
                "role": role,
                "content": content,
                "created_by_user_id": created_by_user_id,
                "metadata": _json(metadata or {}),
            },
        )
        self.session.flush()
        return message_id

    def add_case_user_message(
        self,
        *,
        organization_id: str,
        case_id: str,
        user_id: str,
        content: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_thread_id = thread_id
        if resolved_thread_id:
            if not self.thread_belongs_to_case(case_id=case_id, thread_id=resolved_thread_id):
                raise ValueError(f"Thread does not belong to case: {resolved_thread_id}")
            parent_message_id = self._latest_thread_message_id(resolved_thread_id)
            message_id = self.add_chat_message(
                thread_id=resolved_thread_id,
                role="user",
                content=content,
                created_by_user_id=user_id,
                parent_message_id=parent_message_id,
                metadata={"source": "case_workspace_ui"},
            )
        else:
            resolved_thread_id = self._latest_case_thread_id(case_id)
            if resolved_thread_id:
                parent_message_id = self._latest_thread_message_id(resolved_thread_id)
                message_id = self.add_chat_message(
                    thread_id=resolved_thread_id,
                    role="user",
                    content=content,
                    created_by_user_id=user_id,
                    parent_message_id=parent_message_id,
                    metadata={"source": "case_workspace_ui"},
                )
            else:
                thread_ids = self.create_chat_thread(
                    organization_id=organization_id,
                    case_id=case_id,
                    created_by_user_id=user_id,
                    title=_chat_thread_title(content),
                    first_user_message=content,
                )
                resolved_thread_id = thread_ids.thread_id
                message_id = thread_ids.first_message_id
        self.session.execute(
            text("UPDATE chat_threads SET updated_at = now() WHERE thread_id = :thread_id"),
            {"thread_id": resolved_thread_id},
        )
        self.session.flush()
        return self._workspace_message(message_id)

    def add_case_assistant_message(
        self,
        *,
        case_id: str,
        thread_id: str,
        content: str,
        parent_message_id: str | None,
        pack_id: str | None = None,
        agent_run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.thread_belongs_to_case(case_id=case_id, thread_id=thread_id):
            raise ValueError(f"Thread does not belong to case: {thread_id}")
        message_metadata = {
            "source": "case_workspace_ui",
            "mode": "pack_bounded_chat",
            **(metadata or {}),
        }
        if pack_id:
            message_metadata["pack_id"] = pack_id
        if agent_run_id:
            message_metadata["agent_run_id"] = agent_run_id
        message_id = self.add_chat_message(
            thread_id=thread_id,
            role="assistant",
            content=content,
            parent_message_id=parent_message_id,
            metadata=message_metadata,
        )
        self.session.execute(
            text("UPDATE chat_threads SET updated_at = now() WHERE thread_id = :thread_id"),
            {"thread_id": thread_id},
        )
        self.session.flush()
        return self._workspace_message(message_id)

    def _latest_case_thread_id(self, case_id: str) -> str | None:
        row = self.session.execute(
            text(
                """
                SELECT thread_id
                FROM chat_threads
                WHERE case_id = :case_id
                  AND status = 'active'
                ORDER BY updated_at DESC, created_at DESC, thread_id DESC
                LIMIT 1
                """
            ),
            {"case_id": case_id},
        ).scalar()
        return str(row) if row is not None else None

    def _latest_thread_message_id(self, thread_id: str) -> str | None:
        row = self.session.execute(
            text(
                """
                SELECT message_id
                FROM chat_messages
                WHERE thread_id = :thread_id
                  AND status = 'complete'
                ORDER BY created_at DESC, message_id DESC
                LIMIT 1
                """
            ),
            {"thread_id": thread_id},
        ).scalar()
        return str(row) if row is not None else None

    def _workspace_message(self, message_id: str) -> dict[str, Any]:
        row = self.session.execute(
            text(
                """
                SELECT
                    cm.message_id,
                    cm.thread_id,
                    cm.role,
                    cm.content,
                    cm.created_at,
                    cm.metadata->>'pack_id' AS pack_id
                FROM chat_messages cm
                WHERE cm.message_id = :message_id
                """
            ),
            {"message_id": message_id},
        ).mappings().one()
        return {
            "messageId": str(row["message_id"]),
            "threadId": str(row["thread_id"]),
            "role": str(row["role"]),
            "content": str(row["content"]),
            "createdAt": row["created_at"],
            "packId": str(row["pack_id"]) if row["pack_id"] else None,
        }

    def add_case_fact(
        self,
        *,
        case_id: str,
        raw_input_id: str,
        fact_text: str,
        fact_category: str,
        certainty_label: str,
        extracted_by_agent_run_id: str,
        source_span_start: int | None = None,
        source_span_end: int | None = None,
        source_quote: str | None = None,
        materiality: str = "unknown",
        disputed_status: str = "unknown",
    ) -> str:
        fact_id = new_id("fact")
        self.session.execute(
            text(
                """
                INSERT INTO case_facts (
                    fact_id, case_id, raw_input_id, fact_text, fact_category,
                    certainty_label, materiality, disputed_status, source_span_start,
                    source_span_end, source_quote, extracted_by_agent_run_id
                )
                VALUES (
                    :fact_id, :case_id, :raw_input_id, :fact_text, :fact_category,
                    :certainty_label, :materiality, :disputed_status, :source_span_start,
                    :source_span_end, :source_quote, :extracted_by_agent_run_id
                )
                """
            ),
            {
                "fact_id": fact_id,
                "case_id": case_id,
                "raw_input_id": raw_input_id,
                "fact_text": fact_text,
                "fact_category": fact_category,
                "certainty_label": certainty_label,
                "materiality": materiality,
                "disputed_status": disputed_status,
                "source_span_start": source_span_start,
                "source_span_end": source_span_end,
                "source_quote": source_quote,
                "extracted_by_agent_run_id": extracted_by_agent_run_id,
            },
        )
        self.session.flush()
        return fact_id

    def add_case_issue(
        self,
        *,
        case_id: str,
        issue_text: str,
        issue_type: str,
        created_by_agent_run_id: str,
        status: str = "candidate",
        inferred_reason: str | None = None,
    ) -> str:
        issue_id = new_id("issue")
        self.session.execute(
            text(
                """
                INSERT INTO case_issues (
                    issue_id, case_id, issue_text, issue_type, status,
                    inferred_reason, created_by_agent_run_id
                )
                VALUES (
                    :issue_id, :case_id, :issue_text, :issue_type, :status,
                    :inferred_reason, :created_by_agent_run_id
                )
                """
            ),
            {
                "issue_id": issue_id,
                "case_id": case_id,
                "issue_text": issue_text,
                "issue_type": issue_type,
                "status": status,
                "inferred_reason": inferred_reason,
                "created_by_agent_run_id": created_by_agent_run_id,
            },
        )
        self.session.flush()
        return issue_id

    def first_retrieval_chunk(self) -> dict[str, Any]:
        row = self.session.execute(
            text(
                """
                SELECT chunk_id, document_id, title, citation, page_start, page_end, chunk_text
                FROM retrieval_chunks
                ORDER BY authority_level ASC, year DESC NULLS LAST, chunk_id ASC
                LIMIT 1
                """
            )
        ).mappings().one()
        return dict(row)

    def create_research_pack_with_chunk(
        self,
        *,
        case_id: str,
        thread_id: str,
        agent_run_id: str,
        user_id: str,
        query: str,
        query_class: str,
        chunk_id: str,
        selected_text: str,
        purpose: str = "initial_research",
    ) -> ResearchPackIds:
        pack_id = new_id("pack")
        pack_item_id = f"{pack_id}_item_001"
        self.session.execute(
            text(
                """
                INSERT INTO research_packs (
                    pack_id, case_id, source_thread_id, source_agent_run_id, query,
                    query_class, status, token_budget, retrieval_config
                )
                VALUES (
                    :pack_id, :case_id, :thread_id, :agent_run_id, :query,
                    :query_class, 'complete', 12000, '{"mode":"single_chunk_repository_insert"}'::jsonb
                )
                """
            ),
            {
                "pack_id": pack_id,
                "case_id": case_id,
                "thread_id": thread_id,
                "agent_run_id": agent_run_id,
                "query": query,
                "query_class": query_class,
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO research_pack_items (
                    pack_item_id, pack_id, chunk_id, rank, fused_score,
                    selection_reason, selected_text
                )
                VALUES (
                    :pack_item_id, :pack_id, :chunk_id, 1, 1.0,
                    'single chunk selected by repository workflow', :selected_text
                )
                """
            ),
            {
                "pack_item_id": pack_item_id,
                "pack_id": pack_id,
                "chunk_id": chunk_id,
                "selected_text": selected_text[:1000],
            },
        )
        self.session.execute(
            text(
                """
                INSERT INTO case_research_packs (
                    case_id, pack_id, purpose, created_by_agent_run_id, created_by_user_id
                )
                VALUES (:case_id, :pack_id, :purpose, :agent_run_id, :user_id)
                """
            ),
            {
                "case_id": case_id,
                "pack_id": pack_id,
                "purpose": purpose,
                "agent_run_id": agent_run_id,
                "user_id": user_id,
            },
        )
        self.session.flush()
        return ResearchPackIds(pack_id=pack_id, pack_item_id=pack_item_id)

    def save_research_pack(
        self,
        *,
        pack: LegalResearchPack,
        case_id: str | None = None,
        source_thread_id: str | None = None,
        source_agent_run_id: str | None = None,
        created_by_user_id: str | None = None,
        purpose: str = "legal_research",
    ) -> PersistedResearchPack:
        pack = require_valid_research_pack_contract(seal_research_pack(pack))
        pack_hash = pack.pack_hash or research_pack_hash(pack)
        sealed_payload = _json(pack.model_dump(mode="json"))
        existing = self.session.execute(
            text(
                """
                SELECT pack_hash, pack_version, sealed_payload
                FROM research_packs
                WHERE pack_id = :pack_id
                """
            ),
            {"pack_id": pack.pack_id},
        ).mappings().first()
        if existing is not None:
            existing_hash = str(existing["pack_hash"]) if existing["pack_hash"] else None
            if existing_hash != pack_hash:
                raise ValueError(
                    "Research pack immutability violation: pack_id already exists with different canonical content"
                )
            if existing["sealed_payload"] is None:
                self.session.execute(
                    text(
                        """
                        UPDATE research_packs
                        SET sealed_payload = CAST(:sealed_payload AS jsonb)
                        WHERE pack_id = :pack_id
                          AND sealed_payload IS NULL
                        """
                    ),
                    {"pack_id": pack.pack_id, "sealed_payload": sealed_payload},
                )
            self._link_research_pack_to_case(
                case_id=case_id,
                pack_id=pack.pack_id,
                purpose=purpose,
                source_agent_run_id=source_agent_run_id,
                created_by_user_id=created_by_user_id,
            )
            self._upsert_relevance_for_research_pack(case_id=case_id, pack=pack)
            item_count = self.session.execute(
                text("SELECT count(*) FROM research_pack_items WHERE pack_id = :pack_id"),
                {"pack_id": pack.pack_id},
            ).scalar_one()
            self.session.flush()
            return PersistedResearchPack(pack_id=pack.pack_id, item_count=int(item_count), pack_hash=pack_hash)

        token_budget = int(pack.retrieval_config.get("max_tokens") or 0) or None
        self.session.execute(
            text(
                """
                INSERT INTO research_packs (
                    pack_id, case_id, source_thread_id, source_agent_run_id,
                    schema_version, pack_version, parent_pack_id, query, query_class,
                    filters, retrieval_config, status, missing_source_summary,
                    token_budget, token_count, source_warning_count, source_warnings,
                    retrieval_trace, pack_hash, sealed_payload, created_at
                )
                VALUES (
                    :pack_id, :case_id, :source_thread_id, :source_agent_run_id,
                    :schema_version, :pack_version, :parent_pack_id, :query,
                    :query_class, CAST(:filters AS jsonb),
                    CAST(:retrieval_config AS jsonb), 'complete',
                    :missing_source_summary, :token_budget, :token_count,
                    :source_warning_count, :source_warnings,
                    CAST(:retrieval_trace AS jsonb), :pack_hash,
                    CAST(:sealed_payload AS jsonb), :created_at
                )
                """
            ),
            {
                "pack_id": pack.pack_id,
                "case_id": case_id,
                "source_thread_id": source_thread_id,
                "source_agent_run_id": source_agent_run_id,
                "schema_version": pack.schema_version,
                "pack_version": pack.pack_version,
                "parent_pack_id": pack.parent_pack_id,
                "query": pack.query,
                "query_class": pack.query_class.value,
                "filters": _json(pack.filters.model_dump(mode="json")),
                "retrieval_config": _json(pack.retrieval_config),
                "missing_source_summary": pack.missing_source_summary,
                "token_budget": token_budget,
                "token_count": pack.token_count,
                "source_warning_count": len(pack.source_warnings),
                "source_warnings": pack.source_warnings,
                "retrieval_trace": _json(pack.retrieval_trace),
                "pack_hash": pack_hash,
                "sealed_payload": sealed_payload,
                "created_at": pack.created_at,
            },
        )
        for rank, item in enumerate(pack.items, start=1):
            self.session.execute(
                text(
                    """
                    INSERT INTO research_pack_items (
                        pack_item_id, pack_id, chunk_id, rank, fused_score,
                        selection_reason, selected_text, page_start, page_end,
                        authority_score, source_quality_flags, token_estimate,
                        scoring_breakdown, retrieval_trace
                    )
                    VALUES (
                        :pack_item_id, :pack_id, :chunk_id, :rank, :fused_score,
                        :selection_reason, :selected_text, :page_start, :page_end,
                        :authority_score, :source_quality_flags, :token_estimate,
                        CAST(:scoring_breakdown AS jsonb),
                        CAST(:retrieval_trace AS jsonb)
                    )
                    """
                ),
                {
                    "pack_item_id": item.pack_item_id,
                    "pack_id": pack.pack_id,
                    "chunk_id": item.chunk_id,
                    "rank": rank,
                    "fused_score": item.fused_score,
                    "selection_reason": item.selection_reason,
                    "selected_text": item.text,
                    "page_start": item.page_start,
                    "page_end": item.page_end,
                    "authority_score": round(1.0 / max(1, item.authority_level), 6),
                    "source_quality_flags": list(item.metadata.get("quality_flags", [])),
                    "token_estimate": item.token_estimate,
                    "scoring_breakdown": _json(item.scoring_breakdown),
                    "retrieval_trace": _json(item.retrieval_trace),
                },
            )
            self.replace_pack_item_source_anchors(
                pack_id=pack.pack_id,
                pack_item_id=item.pack_item_id,
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                selected_text=item.text,
                page_start=item.page_start,
                page_end=item.page_end,
            )
        self._link_research_pack_to_case(
            case_id=case_id,
            pack_id=pack.pack_id,
            purpose=purpose,
            source_agent_run_id=source_agent_run_id,
            created_by_user_id=created_by_user_id,
        )
        self._upsert_relevance_for_research_pack(case_id=case_id, pack=pack)
        retriever_counts = pack.retrieval_config.get("retriever_counts") or {}
        self.session.execute(
            text(
                """
                INSERT INTO retrieval_events (
                    pack_id, query, query_class, filters, keyword_hits, vector_hits,
                    graph_hits, selected_items, retrieval_trace, parent_pack_id,
                    pack_version
                )
                VALUES (
                    :pack_id, :query, :query_class, CAST(:filters AS jsonb),
                    :keyword_hits, :vector_hits, 0, :selected_items,
                    CAST(:retrieval_trace AS jsonb), :parent_pack_id,
                    :pack_version
                )
                """
            ),
            {
                "pack_id": pack.pack_id,
                "query": pack.query,
                "query_class": pack.query_class.value,
                "filters": _json(pack.filters.model_dump(mode="json")),
                "keyword_hits": int(retriever_counts.get("opensearch_bm25_phrase_fuzzy") or 0),
                "vector_hits": int(retriever_counts.get("qdrant_dense_vector") or 0),
                "selected_items": len(pack.items),
                "retrieval_trace": _json(pack.retrieval_trace),
                "parent_pack_id": pack.parent_pack_id,
                "pack_version": pack.pack_version,
            },
        )
        self.session.flush()
        return PersistedResearchPack(pack_id=pack.pack_id, item_count=len(pack.items), pack_hash=pack_hash)

    def load_research_pack(self, pack_id: str) -> LegalResearchPack | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    pack_id, schema_version, pack_version, parent_pack_id,
                    query, query_class, filters, retrieval_config,
                    missing_source_summary, token_count, source_warnings,
                    retrieval_trace, pack_hash, created_at, sealed_payload
                FROM research_packs
                WHERE pack_id = :pack_id
                """
            ),
            {"pack_id": pack_id},
        ).mappings().first()
        if row is None:
            return None

        sealed_payload = row["sealed_payload"]
        if sealed_payload is not None:
            pack = LegalResearchPack.model_validate(_json_value(sealed_payload))
            sealed = require_valid_research_pack_contract(pack)
            stored_hash = str(row["pack_hash"]) if row["pack_hash"] else None
            if stored_hash and sealed.pack_hash != stored_hash:
                raise ValueError("Persisted research pack hash does not match sealed payload")
            return sealed

        item_rows = self.session.execute(
            text(
                """
                SELECT
                    rpi.pack_item_id, rpi.chunk_id, rpi.rank, rpi.fused_score,
                    rpi.selection_reason, rpi.selected_text, rpi.page_start AS pack_page_start,
                    rpi.page_end AS pack_page_end, rpi.token_estimate AS pack_token_estimate,
                    rpi.scoring_breakdown, rpi.retrieval_trace,
                    COALESCE(rpi.source_quality_flags, '{}'::text[]) AS source_quality_flags,
                    rc.document_id, rc.title, rc.document_type, rc.source_id,
                    rc.authority_level, rc.year, rc.citation, rc.page_start,
                    rc.page_end, rc.chunk_text, rc.source_url, rc.local_path,
                    rc.token_estimate, rc.metadata
                FROM research_pack_items rpi
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                WHERE rpi.pack_id = :pack_id
                ORDER BY rpi.rank ASC, rpi.pack_item_id ASC
                """
            ),
            {"pack_id": pack_id},
        ).mappings().all()
        items: list[dict[str, Any]] = []
        for item_row in item_rows:
            metadata = dict(_json_value(item_row["metadata"]) or {})
            quality_flags = list(item_row["source_quality_flags"] or metadata.get("quality_flags", []))
            metadata["quality_flags"] = sorted(set(str(flag) for flag in quality_flags))
            items.append(
                {
                    "pack_item_id": str(item_row["pack_item_id"]),
                    "chunk_id": str(item_row["chunk_id"]),
                    "document_id": str(item_row["document_id"]),
                    "title": str(item_row["title"]),
                    "document_type": str(item_row["document_type"]),
                    "source_id": str(item_row["source_id"]),
                    "authority_level": int(item_row["authority_level"]),
                    "year": int(item_row["year"]) if item_row["year"] is not None else None,
                    "citation": str(item_row["citation"]),
                    "page_start": item_row["pack_page_start"] if item_row["pack_page_start"] is not None else item_row["page_start"],
                    "page_end": item_row["pack_page_end"] if item_row["pack_page_end"] is not None else item_row["page_end"],
                    "text": str(item_row["selected_text"] or item_row["chunk_text"]),
                    "fused_score": float(item_row["fused_score"]),
                    "selection_reason": str(item_row["selection_reason"]),
                    "source_url": str(item_row["source_url"]) if item_row["source_url"] else None,
                    "local_path": str(item_row["local_path"]) if item_row["local_path"] else None,
                    "token_estimate": int(item_row["pack_token_estimate"] or item_row["token_estimate"] or 0) or None,
                    "scoring_breakdown": _json_value(item_row["scoring_breakdown"]) or {},
                    "retrieval_trace": _json_value(item_row["retrieval_trace"]) or [],
                    "metadata": metadata,
                }
            )

        pack = LegalResearchPack.model_validate(
            {
                "schema_version": str(row["schema_version"] or "legal_research_pack.v1"),
                "pack_id": str(row["pack_id"]),
                "pack_version": int(row["pack_version"] or 1),
                "parent_pack_id": str(row["parent_pack_id"]) if row["parent_pack_id"] else None,
                "query": str(row["query"]),
                "query_class": str(row["query_class"]),
                "filters": _json_value(row["filters"]) or {},
                "retrieval_config": _json_value(row["retrieval_config"]) or {},
                "items": items,
                "missing_source_summary": str(row["missing_source_summary"]) if row["missing_source_summary"] else None,
                "token_count": int(row["token_count"]) if row["token_count"] is not None else None,
                "source_warnings": list(row["source_warnings"] or []),
                "retrieval_trace": _json_value(row["retrieval_trace"]) or [],
                "pack_hash": str(row["pack_hash"]) if row["pack_hash"] else None,
                "created_at": row["created_at"],
            }
        )
        return seal_research_pack(pack, parent_pack_id=pack.parent_pack_id, pack_version=pack.pack_version)

    def _link_research_pack_to_case(
        self,
        *,
        case_id: str | None,
        pack_id: str,
        purpose: str,
        source_agent_run_id: str | None,
        created_by_user_id: str | None,
    ) -> None:
        if not case_id:
            return
        self.session.execute(
            text(
                """
                INSERT INTO case_research_packs (
                    case_id, pack_id, purpose, created_by_agent_run_id, created_by_user_id
                )
                VALUES (:case_id, :pack_id, :purpose, :agent_run_id, :user_id)
                ON CONFLICT (case_id, pack_id) DO UPDATE SET
                    purpose = EXCLUDED.purpose,
                    created_by_agent_run_id = EXCLUDED.created_by_agent_run_id,
                    created_by_user_id = EXCLUDED.created_by_user_id
                """
            ),
            {
                "case_id": case_id,
                "pack_id": pack_id,
                "purpose": purpose,
                "agent_run_id": source_agent_run_id,
                "user_id": created_by_user_id,
            },
        )

    def research_pack_item_ids(self, pack_id: str) -> list[str]:
        rows = self.session.execute(
            text(
                """
                SELECT pack_item_id
                FROM research_pack_items
                WHERE pack_id = :pack_id
                ORDER BY rank ASC, pack_item_id ASC
                """
            ),
            {"pack_id": pack_id},
        ).scalars()
        return [str(row) for row in rows]

    def _upsert_relevance_for_research_pack(self, *, case_id: str | None, pack: LegalResearchPack) -> None:
        if not case_id or not pack.items:
            return
        document_scores: dict[str, dict[str, Any]] = {}
        for item in pack.items:
            score = max(0.0, min(1.0, float(item.fused_score or 0.0)))
            legal_quality_multiplier = (
                item.metadata.get("legal_quality_multiplier")
                if item.metadata
                else None
            )
            if legal_quality_multiplier is None:
                legal_quality_multiplier = (item.scoring_breakdown or {}).get("legal_quality_multiplier")
            try:
                confidence = score * float(legal_quality_multiplier if legal_quality_multiplier is not None else 1.0)
            except (TypeError, ValueError):
                confidence = score
            confidence = max(0.0, min(1.0, confidence))
            current = document_scores.setdefault(
                item.document_id,
                {
                    "relevance_score": 0.0,
                    "confidence_score": 0.0,
                    "evidence": [],
                    "title": item.title,
                    "citation": item.citation,
                },
            )
            current["relevance_score"] = max(float(current["relevance_score"]), score)
            current["confidence_score"] = max(float(current["confidence_score"]), confidence)
            current["evidence"].append(
                {
                    "pack_item_id": item.pack_item_id,
                    "chunk_id": item.chunk_id,
                    "fused_score": score,
                    "confidence_score": confidence,
                    "citation": item.citation,
                    "page_start": item.page_start,
                    "page_end": item.page_end,
                    "selection_reason": item.selection_reason,
                    "quality_flags": list((item.metadata or {}).get("quality_flags", [])),
                }
            )

        for document_id, relevance in document_scores.items():
            relevance_score = round(float(relevance["relevance_score"]), 6)
            confidence_score = round(float(relevance["confidence_score"]), 6)
            relevance_band = _relevance_band(relevance_score)
            relevance_id = _stable_relevance_id(case_id=case_id, document_id=document_id, source="retrieval")
            evidence = sorted(
                relevance["evidence"],
                key=lambda item: (-float(item["relevance_score"] if "relevance_score" in item else item["fused_score"]), str(item["pack_item_id"])),
            )
            rationale = (
                f"Selected by research pack {pack.pack_id} for query {pack.query!r}; "
                f"highest retrieval relevance score {relevance_score:.3f}."
            )
            self.session.execute(
                text(
                    """
                    INSERT INTO case_document_relevance (
                        relevance_id, case_id, document_id, relevance_score,
                        confidence_score, relevance_band, source, status,
                        rationale, query_text, evidence, research_pack_id, metadata
                    )
                    VALUES (
                        :relevance_id, :case_id, :document_id, :relevance_score,
                        :confidence_score, :relevance_band, 'retrieval', 'candidate',
                        :rationale, :query_text, CAST(:evidence AS jsonb),
                        :research_pack_id, CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (case_id, document_id, source)
                    WHERE document_id IS NOT NULL AND case_document_id IS NULL
                    DO UPDATE SET
                        relevance_score = GREATEST(case_document_relevance.relevance_score, EXCLUDED.relevance_score),
                        confidence_score = GREATEST(COALESCE(case_document_relevance.confidence_score, 0), COALESCE(EXCLUDED.confidence_score, 0)),
                        relevance_band = CASE
                            WHEN GREATEST(case_document_relevance.relevance_score, EXCLUDED.relevance_score) >= 0.95 THEN 'direct'
                            WHEN GREATEST(case_document_relevance.relevance_score, EXCLUDED.relevance_score) >= 0.75 THEN 'strong'
                            WHEN GREATEST(case_document_relevance.relevance_score, EXCLUDED.relevance_score) >= 0.45 THEN 'moderate'
                            WHEN GREATEST(case_document_relevance.relevance_score, EXCLUDED.relevance_score) >= 0.10 THEN 'weak'
                            WHEN GREATEST(case_document_relevance.relevance_score, EXCLUDED.relevance_score) > 0 THEN 'background'
                            ELSE 'irrelevant'
                        END,
                        status = CASE
                            WHEN case_document_relevance.status = 'rejected' THEN 'candidate'
                            ELSE case_document_relevance.status
                        END,
                        rationale = EXCLUDED.rationale,
                        query_text = EXCLUDED.query_text,
                        evidence = EXCLUDED.evidence,
                        research_pack_id = EXCLUDED.research_pack_id,
                        metadata = EXCLUDED.metadata,
                        updated_at = now()
                    """
                ),
                {
                    "relevance_id": relevance_id,
                    "case_id": case_id,
                    "document_id": document_id,
                    "relevance_score": relevance_score,
                    "confidence_score": confidence_score,
                    "relevance_band": relevance_band,
                    "rationale": rationale,
                    "query_text": pack.query,
                    "evidence": _json(evidence),
                    "research_pack_id": pack.pack_id,
                    "metadata": _json(
                        {
                            "query_class": pack.query_class.value,
                            "document_title": relevance["title"],
                            "citation": relevance["citation"],
                        }
                    ),
                },
            )

    def research_pack_access_context(self, pack_id: str) -> ResearchPackAccessContext | None:
        row = self.session.execute(
            text(
                """
                SELECT pack_id, case_id
                FROM research_packs
                WHERE pack_id = :pack_id
                """
            ),
            {"pack_id": pack_id},
        ).mappings().first()
        if row is None:
            return None

        case_ids: list[str] = []
        if row["case_id"]:
            case_ids.append(str(row["case_id"]))

        linked_rows = self.session.execute(
            text(
                """
                SELECT DISTINCT case_id
                FROM case_research_packs
                WHERE pack_id = :pack_id
                  AND status = 'active'
                ORDER BY case_id ASC
                """
            ),
            {"pack_id": pack_id},
        ).scalars()
        for linked_case_id in linked_rows:
            case_id = str(linked_case_id)
            if case_id not in case_ids:
                case_ids.append(case_id)

        return ResearchPackAccessContext(pack_id=str(row["pack_id"]), case_ids=tuple(case_ids))

    def research_pack_version(self, pack_id: str) -> int | None:
        row = self.session.execute(
            text(
                """
                SELECT pack_version
                FROM research_packs
                WHERE pack_id = :pack_id
                """
            ),
            {"pack_id": pack_id},
        ).scalar()
        return int(row) if row is not None else None

    def next_child_research_pack_version(self, parent_pack_id: str) -> int:
        row = self.session.execute(
            text(
                """
                SELECT GREATEST(
                    COALESCE((SELECT pack_version FROM research_packs WHERE pack_id = :parent_pack_id), 1),
                    COALESCE((SELECT max(pack_version) FROM research_packs WHERE parent_pack_id = :parent_pack_id), 1)
                ) + 1
                """
            ),
            {"parent_pack_id": parent_pack_id},
        ).scalar_one()
        return int(row)

    def get_pack_item_source(self, *, pack_id: str, pack_item_id: str) -> PackItemSourceResponse | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    rp.pack_id,
                    rp.retrieval_config,
                    rpi.pack_item_id,
                    rpi.chunk_id,
                    rpi.rank,
                    rpi.fused_score,
                    rpi.selection_reason,
                    rpi.selected_text,
                    rpi.page_start AS item_page_start,
                    rpi.page_end AS item_page_end,
                    rpi.source_quality_flags AS item_quality_flags,
                    rpi.token_estimate,
                    rpi.scoring_breakdown,
                    rpi.retrieval_trace AS item_retrieval_trace,
                    rc.document_id,
                    rc.source_id,
                    rc.document_type,
                    rc.title,
                    rc.year,
                    rc.authority_level,
                    rc.page_start AS chunk_page_start,
                    rc.page_end AS chunk_page_end,
                    rc.chunk_text,
                    rc.citation,
                    rc.source_url AS chunk_source_url,
                    rc.local_path AS chunk_local_path,
                    rc.quality_flags AS chunk_quality_flags,
                    rc.metadata AS chunk_metadata,
                    d.source_url AS document_source_url,
                    d.local_path AS document_local_path
                FROM research_pack_items rpi
                JOIN research_packs rp ON rp.pack_id = rpi.pack_id
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                JOIN documents d ON d.document_id = rc.document_id
                WHERE rpi.pack_id = :pack_id
                  AND rpi.pack_item_id = :pack_item_id
                """
            ),
            {"pack_id": pack_id, "pack_item_id": pack_item_id},
        ).mappings().first()
        if row is None:
            return None

        data = dict(row)
        page_start = data.get("item_page_start") or data.get("chunk_page_start")
        page_end = data.get("item_page_end") or data.get("chunk_page_end")
        pages = self._source_pages(str(data["document_id"]), page_start, page_end)
        anchors = self._source_anchors(pack_item_id)
        selected_text = str(data.get("selected_text") or data.get("chunk_text") or "")

        if pages:
            context_text = "\n\n".join(page["text"] for page in pages)
            context_source = "page_text"
        elif data.get("selected_text"):
            context_text = selected_text
            context_source = "research_pack_item"
        else:
            context_text = str(data.get("chunk_text") or "")
            context_source = "retrieval_chunk"

        local_path = data.get("chunk_local_path") or data.get("document_local_path")
        absolute_local_path, local_file_exists = resolve_local_path(local_path)
        quality_flags = list(data.get("item_quality_flags") or data.get("chunk_quality_flags") or [])
        retrieval_metadata = {
            "rank": data.get("rank"),
            "fused_score": float(data["fused_score"]) if data.get("fused_score") is not None else None,
            "selection_reason": data.get("selection_reason"),
            "token_estimate": int(data["token_estimate"]) if data.get("token_estimate") is not None else None,
            "scoring_breakdown": data.get("scoring_breakdown") or {},
            "item_retrieval_trace": data.get("item_retrieval_trace") or [],
            "retrieval_config": data.get("retrieval_config") or {},
            "chunk_metadata": data.get("chunk_metadata") or {},
        }

        return PackItemSourceResponse.model_validate(
            {
                "pack_id": data["pack_id"],
                "pack_item_id": data["pack_item_id"],
                "chunk_id": data["chunk_id"],
                "document_id": data["document_id"],
                "title": data["title"],
                "document_type": data["document_type"],
                "source_id": data["source_id"],
                "authority_level": data["authority_level"],
                "year": data.get("year"),
                "citation": data["citation"],
                "page_start": page_start,
                "page_end": page_end,
                "selected_text": selected_text,
                "context_text": context_text,
                "context_source": context_source,
                "source_url": data.get("chunk_source_url") or data.get("document_source_url"),
                "local_path": local_path,
                "absolute_local_path": absolute_local_path,
                "local_file_exists": local_file_exists,
                "page_text_available": bool(pages),
                "pages": pages,
                "anchors": anchors,
                "anchor_status": "anchored" if anchors else "not_anchored",
                "source_quality_flags": quality_flags,
                "retrieval_metadata": retrieval_metadata,
            }
        )

    def replace_pack_item_source_anchors(
        self,
        *,
        pack_id: str,
        pack_item_id: str,
        chunk_id: str,
        document_id: str,
        selected_text: str,
        page_start: int | None,
        page_end: int | None,
    ) -> list[SourceAnchor]:
        pages = [
            PageText(page_id=page["page_id"], page_number=page["page_number"], text=page["text"])
            for page in self._source_pages(document_id, page_start, page_end)
        ]
        anchors = build_source_anchors(
            pack_id=pack_id,
            pack_item_id=pack_item_id,
            chunk_id=chunk_id,
            document_id=document_id,
            selected_text=selected_text,
            pages=pages,
        )
        self.session.execute(
            text("DELETE FROM pack_item_source_anchors WHERE pack_item_id = :pack_item_id"),
            {"pack_item_id": pack_item_id},
        )
        for anchor in anchors:
            self.session.execute(
                text(
                    """
                    INSERT INTO pack_item_source_anchors (
                        anchor_id, pack_id, pack_item_id, chunk_id, document_id,
                        page_id, page_number, anchor_index, char_start, char_end,
                        quote, match_method, confidence, metadata
                    )
                    VALUES (
                        :anchor_id, :pack_id, :pack_item_id, :chunk_id, :document_id,
                        :page_id, :page_number, :anchor_index, :char_start, :char_end,
                        :quote, :match_method, :confidence, CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (pack_item_id, anchor_index) DO UPDATE SET
                        page_id = EXCLUDED.page_id,
                        page_number = EXCLUDED.page_number,
                        char_start = EXCLUDED.char_start,
                        char_end = EXCLUDED.char_end,
                        quote = EXCLUDED.quote,
                        match_method = EXCLUDED.match_method,
                        confidence = EXCLUDED.confidence,
                        metadata = EXCLUDED.metadata
                    """
                ),
                {
                    "anchor_id": anchor.anchor_id,
                    "pack_id": anchor.pack_id,
                    "pack_item_id": anchor.pack_item_id,
                    "chunk_id": anchor.chunk_id,
                    "document_id": anchor.document_id,
                    "page_id": anchor.page_id,
                    "page_number": anchor.page_number,
                    "anchor_index": anchor.anchor_index,
                    "char_start": anchor.char_start,
                    "char_end": anchor.char_end,
                    "quote": anchor.quote,
                    "match_method": anchor.match_method,
                    "confidence": anchor.confidence,
                    "metadata": _json(anchor.metadata),
                },
            )
        self.session.flush()
        return anchors

    def backfill_source_anchors(self, *, pack_id: str | None = None, limit_items: int = 0) -> dict[str, int]:
        conditions = ["NOT EXISTS (SELECT 1 FROM pack_item_source_anchors pia WHERE pia.pack_item_id = rpi.pack_item_id)"]
        params: dict[str, Any] = {}
        if pack_id:
            conditions.append("rpi.pack_id = :pack_id")
            params["pack_id"] = pack_id
        limit_sql = "LIMIT :limit_items" if limit_items else ""
        if limit_items:
            params["limit_items"] = limit_items
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    rpi.pack_id,
                    rpi.pack_item_id,
                    rpi.chunk_id,
                    rc.document_id,
                    COALESCE(rpi.selected_text, rc.chunk_text) AS selected_text,
                    COALESCE(rpi.page_start, rc.page_start) AS page_start,
                    COALESCE(rpi.page_end, rc.page_end) AS page_end
                FROM research_pack_items rpi
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                WHERE {' AND '.join(conditions)}
                ORDER BY rpi.created_at ASC, rpi.rank ASC
                {limit_sql}
                """
            ),
            params,
        ).mappings().all()
        processed = 0
        anchored = 0
        anchors_created = 0
        for row in rows:
            anchors = self.replace_pack_item_source_anchors(
                pack_id=str(row["pack_id"]),
                pack_item_id=str(row["pack_item_id"]),
                chunk_id=str(row["chunk_id"]),
                document_id=str(row["document_id"]),
                selected_text=str(row["selected_text"] or ""),
                page_start=int(row["page_start"]) if row["page_start"] is not None else None,
                page_end=int(row["page_end"]) if row["page_end"] is not None else None,
            )
            processed += 1
            if anchors:
                anchored += 1
                anchors_created += len(anchors)
        return {"items_processed": processed, "items_anchored": anchored, "anchors_created": anchors_created}

    def _source_pages(self, document_id: str, page_start: int | None, page_end: int | None) -> list[dict[str, Any]]:
        if page_start is None or page_end is None:
            return []
        rows = self.session.execute(
            text(
                """
                SELECT page_id, page_number, text, extraction_method, ocr_confidence, quality_flags
                FROM pages
                WHERE document_id = :document_id
                  AND page_number BETWEEN :page_start AND :page_end
                ORDER BY page_number ASC
                """
            ),
            {"document_id": document_id, "page_start": page_start, "page_end": page_end},
        ).mappings().all()
        return [
            {
                "page_id": str(row["page_id"]),
                "page_number": int(row["page_number"]),
                "text": str(row["text"]),
                "extraction_method": str(row["extraction_method"]),
                "ocr_confidence": float(row["ocr_confidence"]) if row["ocr_confidence"] is not None else None,
                "quality_flags": list(row["quality_flags"] or []),
            }
            for row in rows
        ]

    def _source_anchors(self, pack_item_id: str) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                SELECT
                    anchor_id, page_id, page_number, anchor_index, char_start, char_end,
                    quote, match_method, confidence, metadata
                FROM pack_item_source_anchors
                WHERE pack_item_id = :pack_item_id
                  AND status = 'active'
                ORDER BY anchor_index ASC
                """
            ),
            {"pack_item_id": pack_item_id},
        ).mappings().all()
        return [
            {
                "anchor_id": str(row["anchor_id"]),
                "page_id": str(row["page_id"]) if row["page_id"] else None,
                "page_number": int(row["page_number"]) if row["page_number"] is not None else None,
                "anchor_index": int(row["anchor_index"]),
                "char_start": int(row["char_start"]) if row["char_start"] is not None else None,
                "char_end": int(row["char_end"]) if row["char_end"] is not None else None,
                "quote": str(row["quote"]),
                "match_method": str(row["match_method"]),
                "confidence": float(row["confidence"]),
                "metadata": dict(row["metadata"] or {}),
            }
            for row in rows
        ]

    def pack_item_source_contexts(self, *, pack_id: str, pack_item_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not pack_item_ids:
            return {}
        rows = self.session.execute(
            text(
                """
                SELECT
                    rpi.pack_item_id,
                    rpi.chunk_id,
                    rpi.rank,
                    rpi.selected_text,
                    COALESCE(rpi.page_start, rc.page_start) AS page_start,
                    COALESCE(rpi.page_end, rc.page_end) AS page_end,
                    rc.document_id,
                    rc.title,
                    rc.document_type,
                    rc.source_id,
                    rc.authority_level,
                    rc.year,
                    rc.citation,
                    rc.source_url,
                    rc.local_path
                FROM research_pack_items rpi
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                WHERE rpi.pack_id = :pack_id
                  AND rpi.pack_item_id = ANY(:pack_item_ids)
                ORDER BY rpi.rank ASC, rpi.pack_item_id ASC
                """
            ),
            {"pack_id": pack_id, "pack_item_ids": pack_item_ids},
        ).mappings().all()
        contexts: dict[str, dict[str, Any]] = {}
        for row in rows:
            pack_item_id = str(row["pack_item_id"])
            contexts[pack_item_id] = {
                "pack_item_id": pack_item_id,
                "chunk_id": str(row["chunk_id"]),
                "document_id": str(row["document_id"]),
                "title": str(row["title"]),
                "document_type": str(row["document_type"]),
                "source_id": str(row["source_id"]),
                "authority_level": int(row["authority_level"]),
                "year": int(row["year"]) if row["year"] is not None else None,
                "citation": str(row["citation"]),
                "page_start": int(row["page_start"]) if row["page_start"] is not None else None,
                "page_end": int(row["page_end"]) if row["page_end"] is not None else None,
                "source_url": str(row["source_url"]) if row["source_url"] else None,
                "local_path": str(row["local_path"]) if row["local_path"] else None,
                "selected_text_hash": _sha256(str(row["selected_text"] or "")),
                "anchors": self._source_anchors(pack_item_id),
            }
        return contexts

    def create_draft(
        self,
        *,
        case_id: str,
        thread_id: str | None,
        pack_id: str,
        draft_type: str,
        title: str,
        content_markdown: str,
        created_by_agent_run_id: str | None,
        created_by_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        draft_id = new_id("draft")
        self.session.execute(
            text(
                """
                INSERT INTO drafts (
                    draft_id, case_id, thread_id, pack_id, draft_type, title,
                    content_markdown, created_by_agent_run_id, created_by_user_id,
                    metadata
                )
                VALUES (
                    :draft_id, :case_id, :thread_id, :pack_id, :draft_type, :title,
                    :content_markdown, :created_by_agent_run_id, :created_by_user_id,
                    CAST(:metadata AS jsonb)
                )
                """
            ),
            {
                "draft_id": draft_id,
                "case_id": case_id,
                "thread_id": thread_id,
                "pack_id": pack_id,
                "draft_type": draft_type,
                "title": title,
                "content_markdown": content_markdown,
                "created_by_agent_run_id": created_by_agent_run_id,
                "created_by_user_id": created_by_user_id,
                "metadata": _json(metadata or {}),
            },
        )
        self.session.flush()
        return draft_id

    def add_supported_legal_claim(
        self,
        *,
        case_id: str,
        thread_id: str | None,
        message_id: str | None,
        pack_id: str,
        agent_run_id: str | None,
        claim_text: str,
        pack_item_ids: list[str],
        claim_type: str = "research_finding",
        risk_level: str = "unknown",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        claim_id = new_id("claim")
        self.session.execute(
            text(
                """
                INSERT INTO legal_claims (
                    claim_id, case_id, thread_id, message_id, pack_id, claim_text,
                    claim_type, support_status, risk_level, created_by_agent_run_id,
                    metadata
                )
                VALUES (
                    :claim_id, :case_id, :thread_id, :message_id, :pack_id, :claim_text,
                    :claim_type, 'supported', :risk_level, :agent_run_id,
                    CAST(:metadata AS jsonb)
                )
                """
            ),
            {
                "claim_id": claim_id,
                "case_id": case_id,
                "thread_id": thread_id,
                "message_id": message_id,
                "pack_id": pack_id,
                "claim_text": claim_text,
                "claim_type": claim_type,
                "risk_level": risk_level,
                "agent_run_id": agent_run_id,
                "metadata": _json(metadata or {}),
            },
        )
        for pack_item_id in _dedupe(pack_item_ids):
            self.session.execute(
                text(
                    """
                    INSERT INTO legal_claim_citations (claim_id, pack_item_id, citation_role)
                    VALUES (:claim_id, :pack_item_id, 'support')
                    """
                ),
                {"claim_id": claim_id, "pack_item_id": pack_item_id},
            )
        self.session.flush()
        return claim_id

    def add_claim_evidence_assessment(
        self,
        *,
        case_id: str,
        assessment: ClaimEvidenceAssessmentRequest,
        thread_id: str | None = None,
        message_id: str | None = None,
        agent_run_id: str | None = None,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        pack_item = self._pack_item_context(
            pack_id=assessment.pack_id,
            pack_item_id=assessment.pack_item_id,
        )
        if pack_item is None:
            raise ValueError(f"Pack item not found in research pack: {assessment.pack_item_id}")

        citation_role = assessment.citation_role
        claim_id = assessment.claim_id
        if claim_id:
            claim = self._claim_state_for_metadata(case_id=case_id, claim_id=claim_id)
            if claim is None:
                raise ValueError(f"Claim not found for case: {claim_id}")
            if str(claim.get("pack_id") or assessment.pack_id) != assessment.pack_id:
                raise ValueError("Assessment pack_id must match the claim pack_id")
        else:
            claim_id = new_id("claim")
            self.session.execute(
                text(
                    """
                    INSERT INTO legal_claims (
                        claim_id, case_id, thread_id, message_id, pack_id, claim_text,
                        claim_type, support_status, risk_level, created_by_agent_run_id,
                        metadata
                    )
                    VALUES (
                        :claim_id, :case_id, :thread_id, :message_id, :pack_id, :claim_text,
                        'evidence_assessment', :support_status, :risk_level, :agent_run_id,
                        CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    "claim_id": claim_id,
                    "case_id": case_id,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "pack_id": assessment.pack_id,
                    "claim_text": assessment.claim_text,
                    "support_status": _support_status_for_stance(assessment.stance),
                    "risk_level": assessment.risk_level,
                    "agent_run_id": agent_run_id,
                    "metadata": _json(
                        {
                            "created_by_user_id": created_by_user_id,
                            "schema_version": assessment.schema_version,
                        }
                    ),
                },
            )

        self.session.execute(
            text(
                """
                INSERT INTO legal_claim_citations (claim_id, pack_item_id, citation_role)
                VALUES (:claim_id, :pack_item_id, :citation_role)
                ON CONFLICT (claim_id, pack_item_id, citation_role) DO NOTHING
                """
            ),
            {
                "claim_id": claim_id,
                "pack_item_id": assessment.pack_item_id,
                "citation_role": citation_role,
            },
        )
        self._store_evidence_assessment_metadata(
            case_id=case_id,
            claim_id=claim_id,
            assessment=assessment,
            citation_role=citation_role,
        )
        self.session.flush()
        created = self.list_claim_evidence_assessments(
            case_id=case_id,
            claim_id=claim_id,
            pack_id=assessment.pack_id,
            stance=assessment.stance,
            limit=500,
        )
        for item in created:
            if item["pack_item_id"] == assessment.pack_item_id:
                return item
        raise RuntimeError("Evidence assessment was not readable after persistence")

    def list_claim_evidence_assessments(
        self,
        *,
        case_id: str,
        claim_id: str | None = None,
        pack_id: str | None = None,
        stance: EvidenceStance | str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        citation_role = citation_role_for_evidence_stance(stance) if stance is not None else None
        conditions = ["lc.case_id = :case_id"]
        params: dict[str, Any] = {"case_id": case_id, "limit": limit}
        if claim_id is not None:
            conditions.append("lc.claim_id = :claim_id")
            params["claim_id"] = claim_id
        if pack_id is not None:
            conditions.append("lc.pack_id = :pack_id")
            params["pack_id"] = pack_id
        if citation_role is not None:
            conditions.append("lcc.citation_role = :citation_role")
            params["citation_role"] = citation_role
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    lc.claim_id,
                    lc.case_id,
                    lc.claim_text,
                    lc.pack_id,
                    lc.risk_level,
                    lc.metadata AS claim_metadata,
                    lcc.pack_item_id,
                    lcc.citation_role,
                    rpi.chunk_id,
                    rc.document_id,
                    rc.title,
                    rc.document_type,
                    rc.source_id,
                    rc.authority_level,
                    rc.year,
                    rc.citation,
                    COALESCE(rpi.page_start, rc.page_start) AS page_start,
                    COALESCE(rpi.page_end, rc.page_end) AS page_end,
                    rc.source_url,
                    rc.local_path,
                    COALESCE(rpi.selected_text, rc.chunk_text, '') AS selected_text,
                    count(pia.anchor_id) FILTER (WHERE pia.status = 'active') AS anchor_count,
                    (
                        SELECT ri.status
                        FROM review_items ri
                        WHERE ri.case_id = lc.case_id
                          AND ri.item_type = 'legal_claim'
                          AND ri.item_id = lc.claim_id
                        ORDER BY ri.created_at DESC
                        LIMIT 1
                    ) AS review_status,
                    lcc.created_at AS cited_at
                FROM legal_claims lc
                JOIN legal_claim_citations lcc ON lcc.claim_id = lc.claim_id
                JOIN research_pack_items rpi ON rpi.pack_item_id = lcc.pack_item_id
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                LEFT JOIN pack_item_source_anchors pia ON pia.pack_item_id = lcc.pack_item_id
                WHERE {' AND '.join(conditions)}
                  AND lcc.citation_role IN ('support', 'adverse', 'mixed', 'context')
                GROUP BY
                    lc.claim_id,
                    lc.case_id,
                    lc.claim_text,
                    lc.pack_id,
                    lc.risk_level,
                    lc.metadata,
                    lcc.pack_item_id,
                    lcc.citation_role,
                    rpi.chunk_id,
                    rc.document_id,
                    rc.title,
                    rc.document_type,
                    rc.source_id,
                    rc.authority_level,
                    rc.year,
                    rc.citation,
                    COALESCE(rpi.page_start, rc.page_start),
                    COALESCE(rpi.page_end, rc.page_end),
                    rc.source_url,
                    rc.local_path,
                    COALESCE(rpi.selected_text, rc.chunk_text, ''),
                    lcc.created_at
                ORDER BY lc.created_at DESC, lcc.created_at ASC, lcc.pack_item_id ASC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        return [_evidence_assessment(row) for row in rows]

    def grouped_claim_evidence_assessments(
        self,
        *,
        case_id: str,
        claim_id: str | None = None,
        pack_id: str | None = None,
        stance: EvidenceStance | str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        assessments = self.list_claim_evidence_assessments(
            case_id=case_id,
            claim_id=claim_id,
            pack_id=pack_id,
            stance=stance,
            limit=limit,
        )
        grouped: dict[str, list[dict[str, Any]]] = {
            EvidenceStance.SUPPORTS_CLAIM.value: [],
            EvidenceStance.CONTRADICTS_CLAIM.value: [],
            EvidenceStance.MIXED.value: [],
            EvidenceStance.CONTEXT.value: [],
        }
        for assessment in assessments:
            grouped[str(assessment["stance"])].append(assessment)
        return {
            "case_id": case_id,
            "claim_id": claim_id,
            "pack_id": pack_id,
            "stance": _evidence_stance_value(stance),
            "total_count": len(assessments),
            "groups": [
                {"stance": group_stance, "count": len(items), "items": items}
                for group_stance, items in grouped.items()
                if items or stance is None
            ],
        }

    def create_review_item(
        self,
        *,
        case_id: str,
        item_type: str,
        item_id: str,
        assigned_to_user_id: str | None = None,
        priority: str = "normal",
    ) -> str:
        review_item_id = new_id("review")
        self.session.execute(
            text(
                """
                INSERT INTO review_items (
                    review_item_id, case_id, item_type, item_id, priority, assigned_to_user_id
                )
                VALUES (
                    :review_item_id, :case_id, :item_type, :item_id, :priority, :assigned_to_user_id
                )
                """
            ),
            {
                "review_item_id": review_item_id,
                "case_id": case_id,
                "item_type": item_type,
                "item_id": item_id,
                "priority": priority,
                "assigned_to_user_id": assigned_to_user_id,
            },
        )
        self.session.flush()
        return review_item_id

    def persist_strategy_draft(
        self,
        *,
        case_id: str,
        thread_id: str | None,
        parent_message_id: str | None,
        agent_run_id: str,
        created_by_user_id: str | None,
        assigned_review_user_id: str | None,
        requested_output: str,
        research_pack: LegalResearchPack,
        strategy_response: StrategyDraftResponse,
        agentic_research_plan: AgentResearchPlan | None = None,
        matter_memory: MatterMemory | None = None,
    ) -> PersistedStrategyDraft:
        cited_pack_item_ids = _dedupe(sorted(strategy_response.all_pack_item_ids()))
        stored_pack_item_ids = set(self.research_pack_item_ids(research_pack.pack_id))
        missing_pack_items = sorted(set(cited_pack_item_ids).difference(stored_pack_item_ids))
        if missing_pack_items:
            raise ValueError(
                "Cannot persist strategy draft because cited pack items are not stored: "
                + ", ".join(missing_pack_items)
            )

        citation_contexts = self.pack_item_source_contexts(
            pack_id=research_pack.pack_id,
            pack_item_ids=cited_pack_item_ids,
        )
        pack_hash = research_pack_hash(research_pack)
        agentic_metadata = _agentic_research_metadata(
            agentic_research_plan=agentic_research_plan,
            matter_memory=matter_memory,
        )
        message_id = None
        if thread_id:
            message_id = self.add_chat_message(
                thread_id=thread_id,
                role="assistant",
                content=strategy_response.answer,
                created_by_user_id=created_by_user_id,
                parent_message_id=parent_message_id,
                metadata={
                    "pack_id": research_pack.pack_id,
                    "pack_hash": pack_hash,
                    "requested_output": requested_output,
                    "agent_run_id": agent_run_id,
                    "missing_authorities": strategy_response.missing_authorities,
                    "warnings": strategy_response.warnings,
                    "counterargument_count": len(strategy_response.counterarguments),
                    "risk_count": len(strategy_response.risk_rankings),
                    "next_retrieval_questions": [item.model_dump(mode="json") for item in strategy_response.next_retrieval_questions],
                    "citation_validation": strategy_response.citation_validation,
                    "reasoning_pack": (
                        strategy_response.reasoning_pack.model_dump(mode="json")
                        if strategy_response.reasoning_pack is not None
                        else None
                    ),
                    **agentic_metadata,
                },
            )

        draft_id = self.create_draft(
            case_id=case_id,
            thread_id=thread_id,
            pack_id=research_pack.pack_id,
            draft_type=requested_output,
            title=_draft_title(requested_output, research_pack),
            content_markdown=strategy_response.answer,
            created_by_agent_run_id=agent_run_id,
            created_by_user_id=created_by_user_id,
            metadata={
                "pack_hash": pack_hash,
                "requested_output": requested_output,
                "claim_count": len(strategy_response.claims),
                "missing_authorities": strategy_response.missing_authorities,
                "warnings": strategy_response.warnings,
                "counterarguments": [item.model_dump(mode="json") for item in strategy_response.counterarguments],
                "risk_rankings": [item.model_dump(mode="json") for item in strategy_response.risk_rankings],
                "next_retrieval_questions": [item.model_dump(mode="json") for item in strategy_response.next_retrieval_questions],
                "citation_validation": strategy_response.citation_validation,
                "reasoning_pack": (
                    strategy_response.reasoning_pack.model_dump(mode="json")
                    if strategy_response.reasoning_pack is not None
                    else None
                ),
                **agentic_metadata,
            },
        )
        draft_review_item_id = self.create_review_item(
            case_id=case_id,
            item_type="draft",
            item_id=draft_id,
            assigned_to_user_id=assigned_review_user_id,
            priority="normal",
        )

        claim_ids: list[str] = []
        claim_review_item_ids: list[str] = []
        for claim in strategy_response.claims:
            claim_metadata = {
                "confidence": claim.confidence,
                "pack_hash": pack_hash,
                "draft_id": draft_id,
                "requested_output": requested_output,
                "citations": [
                    citation_contexts.get(pack_item_id, {"pack_item_id": pack_item_id})
                    for pack_item_id in _dedupe(claim.pack_item_ids)
                ],
            }
            claim_id = self.add_supported_legal_claim(
                case_id=case_id,
                thread_id=thread_id,
                message_id=message_id,
                pack_id=research_pack.pack_id,
                agent_run_id=agent_run_id,
                claim_text=claim.claim,
                pack_item_ids=claim.pack_item_ids,
                claim_type="strategy_claim",
                metadata=claim_metadata,
            )
            review_id = self.create_review_item(
                case_id=case_id,
                item_type="legal_claim",
                item_id=claim_id,
                assigned_to_user_id=assigned_review_user_id,
                priority="normal",
            )
            claim_ids.append(claim_id)
            claim_review_item_ids.append(review_id)

        reasoning_review_item_ids: list[str] = []
        if strategy_response.reasoning_pack is not None:
            if strategy_response.reasoning_pack.for_against_brief:
                reasoning_review_item_ids.append(
                    self.create_review_item(
                        case_id=case_id,
                        item_type="adverse_evidence",
                        item_id=draft_id,
                        assigned_to_user_id=assigned_review_user_id,
                        priority="high",
                    )
                )
            if strategy_response.reasoning_pack.missing_evidence_checklist:
                reasoning_review_item_ids.append(
                    self.create_review_item(
                        case_id=case_id,
                        item_type="missing_evidence",
                        item_id=draft_id,
                        assigned_to_user_id=assigned_review_user_id,
                        priority="normal",
                    )
                )

        self.session.flush()
        return PersistedStrategyDraft(
            draft_id=draft_id,
            message_id=message_id,
            agent_run_id=agent_run_id,
            claim_ids=claim_ids,
            draft_review_item_id=draft_review_item_id,
            claim_review_item_ids=claim_review_item_ids,
            reasoning_review_item_ids=reasoning_review_item_ids,
        )

    def list_review_items(
        self,
        *,
        case_id: str,
        status: str | None = "pending",
        item_type: str | None = None,
        item_id: str | None = None,
        review_item_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = ["ri.case_id = :case_id"]
        params: dict[str, Any] = {"case_id": case_id, "limit": limit}
        if status is not None:
            conditions.append("ri.status = :status")
            params["status"] = status
        if item_type is not None:
            conditions.append("ri.item_type = :item_type")
            params["item_type"] = item_type
        if item_id is not None:
            conditions.append("ri.item_id = :item_id")
            params["item_id"] = item_id
        if review_item_id is not None:
            conditions.append("ri.review_item_id = :review_item_id")
            params["review_item_id"] = review_item_id
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    ri.review_item_id,
                    ri.case_id,
                    ri.item_type,
                    ri.item_id,
                    ri.status,
                    ri.priority,
                    ri.assigned_to_user_id,
                    ri.reviewed_by_user_id,
                    ri.decision,
                    ri.comment,
                    ri.due_at,
                    ri.reviewed_at,
                    ri.created_at,
                    ri.updated_at,
                    COALESCE(
                        CASE
                            WHEN ri.item_type = 'adverse_evidence' THEN 'Adverse evidence review'
                            WHEN ri.item_type = 'missing_evidence' THEN 'Missing evidence review'
                            ELSE d.title
                        END,
                        left(lc.claim_text, 160),
                        ri.item_id
                    ) AS item_title,
                    COALESCE(left(d.content_markdown, 500), left(lc.claim_text, 500), '') AS item_excerpt,
                    COALESCE(d.pack_id, lc.pack_id) AS pack_id,
                    COALESCE(d.thread_id, lc.thread_id) AS thread_id
                FROM review_items ri
                LEFT JOIN drafts d
                    ON ri.item_type IN ('draft', 'adverse_evidence', 'missing_evidence')
                   AND d.draft_id = ri.item_id
                   AND d.case_id = ri.case_id
                LEFT JOIN legal_claims lc
                    ON ri.item_type = 'legal_claim'
                   AND lc.claim_id = ri.item_id
                   AND lc.case_id = ri.case_id
                WHERE {' AND '.join(conditions)}
                ORDER BY
                    CASE ri.priority
                        WHEN 'urgent' THEN 0
                        WHEN 'high' THEN 1
                        WHEN 'normal' THEN 2
                        WHEN 'low' THEN 3
                        ELSE 4
                    END,
                    ri.created_at ASC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        return [_plain_dict(row) for row in rows]

    def apply_review_decision(
        self,
        *,
        case_id: str,
        review_item_id: str,
        reviewer_user_id: str,
        decision: str,
        comment: str | None = None,
    ) -> ReviewDecisionResult | None:
        if decision not in {"approved", "rejected", "changes_requested"}:
            raise ValueError(f"Unsupported review decision: {decision}")
        if decision in {"rejected", "changes_requested"} and not (comment or "").strip():
            raise ValueError("comment is required when rejecting or requesting changes")
        if not self.user_has_case_permission(case_id=case_id, user_id=reviewer_user_id):
            raise PermissionError(f"User does not have permission to review this case: {reviewer_user_id}")

        review_before = self._review_item_state_for_update(case_id=case_id, review_item_id=review_item_id)
        if review_before is None:
            return None
        target_before = self._review_target_state(
            case_id=case_id,
            item_type=str(review_before["item_type"]),
            item_id=str(review_before["item_id"]),
        )
        if target_before is None:
            raise ValueError(
                f"Review target not found: {review_before['item_type']} {review_before['item_id']}"
            )

        target_status = _target_status_for_decision(str(review_before["item_type"]), decision)
        self.session.execute(
            text(
                """
                UPDATE review_items
                SET
                    status = :status,
                    decision = :decision,
                    comment = :comment,
                    reviewed_by_user_id = :reviewer_user_id,
                    reviewed_at = now(),
                    updated_at = now()
                WHERE case_id = :case_id
                  AND review_item_id = :review_item_id
                """
            ),
            {
                "case_id": case_id,
                "review_item_id": review_item_id,
                "status": decision,
                "decision": decision,
                "comment": comment,
                "reviewer_user_id": reviewer_user_id,
            },
        )
        if review_before["item_type"] == "draft":
            self.session.execute(
                text(
                    """
                    UPDATE drafts
                    SET status = :target_status, updated_at = now()
                    WHERE case_id = :case_id
                      AND draft_id = :item_id
                    """
                ),
                {"case_id": case_id, "item_id": review_before["item_id"], "target_status": target_status},
            )
        elif review_before["item_type"] == "legal_claim":
            self.session.execute(
                text(
                    """
                    UPDATE legal_claims
                    SET
                        support_status = :target_status,
                        reviewed_by_user_id = :reviewer_user_id,
                        reviewed_at = now(),
                        updated_at = now()
                    WHERE case_id = :case_id
                      AND claim_id = :item_id
                    """
                ),
                {
                    "case_id": case_id,
                    "item_id": review_before["item_id"],
                    "target_status": target_status,
                    "reviewer_user_id": reviewer_user_id,
                },
            )
        elif review_before["item_type"] in {"adverse_evidence", "missing_evidence"}:
            pass
        else:
            raise ValueError(f"Unsupported review item type: {review_before['item_type']}")

        review_after = self.list_review_items(
            case_id=case_id,
            status=None,
            item_id=str(review_before["item_id"]),
            item_type=str(review_before["item_type"]),
            review_item_id=review_item_id,
            limit=1,
        )[0]
        target_after = self._review_target_state(
            case_id=case_id,
            item_type=str(review_before["item_type"]),
            item_id=str(review_before["item_id"]),
        )
        audit_event_id = self._insert_audit_event(
            organization_id=str(review_before["organization_id"]),
            case_id=case_id,
            user_id=reviewer_user_id,
            event_type="review.decision.recorded",
            entity_type="review_item",
            entity_id=review_item_id,
            before_state={
                "review_item": review_before,
                "target": target_before,
            },
            after_state={
                "review_item": review_after,
                "target": target_after,
            },
            metadata={
                "decision": decision,
                "target_item_type": review_before["item_type"],
                "target_item_id": review_before["item_id"],
                "target_status": target_status,
            },
        )
        self.session.flush()
        return ReviewDecisionResult(
            review_item=review_after,
            target_item_type=str(review_before["item_type"]),
            target_item_id=str(review_before["item_id"]),
            target_status=target_status,
            audit_event_id=audit_event_id,
        )

    def list_case_drafts(
        self,
        *,
        case_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = ["d.case_id = :case_id"]
        params: dict[str, Any] = {"case_id": case_id, "limit": limit}
        if status is not None:
            conditions.append("d.status = :status")
            params["status"] = status
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    d.draft_id,
                    d.case_id,
                    d.thread_id,
                    d.pack_id,
                    d.draft_type,
                    d.title,
                    d.status,
                    d.version,
                    left(d.content_markdown, 500) AS content_preview,
                    (
                        SELECT count(*)
                        FROM legal_claims lc
                        WHERE lc.case_id = d.case_id
                          AND lc.metadata->>'draft_id' = d.draft_id
                    ) AS claim_count,
                    (
                        SELECT ri.status
                        FROM review_items ri
                        WHERE ri.case_id = d.case_id
                          AND ri.item_type = 'draft'
                          AND ri.item_id = d.draft_id
                        ORDER BY ri.created_at DESC
                        LIMIT 1
                    ) AS review_status,
                    d.created_by_agent_run_id,
                    d.created_by_user_id,
                    d.created_at,
                    d.updated_at,
                    d.metadata
                FROM drafts d
                WHERE {' AND '.join(conditions)}
                ORDER BY d.updated_at DESC, d.created_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        return [_draft_summary(row) for row in rows]

    def get_draft_detail(self, *, case_id: str, draft_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    d.draft_id,
                    d.case_id,
                    d.thread_id,
                    d.pack_id,
                    d.draft_type,
                    d.title,
                    d.status,
                    d.version,
                    left(d.content_markdown, 500) AS content_preview,
                    d.content_markdown,
                    (
                        SELECT count(*)
                        FROM legal_claims lc
                        WHERE lc.case_id = d.case_id
                          AND lc.metadata->>'draft_id' = d.draft_id
                    ) AS claim_count,
                    (
                        SELECT ri.status
                        FROM review_items ri
                        WHERE ri.case_id = d.case_id
                          AND ri.item_type = 'draft'
                          AND ri.item_id = d.draft_id
                        ORDER BY ri.created_at DESC
                        LIMIT 1
                    ) AS review_status,
                    d.created_by_agent_run_id,
                    d.created_by_user_id,
                    d.created_at,
                    d.updated_at,
                    d.metadata
                FROM drafts d
                WHERE d.case_id = :case_id
                  AND d.draft_id = :draft_id
                """
            ),
            {"case_id": case_id, "draft_id": draft_id},
        ).mappings().first()
        if row is None:
            return None
        data = _draft_summary(row)
        data["content_markdown"] = str(row["content_markdown"])
        data["claims"] = self.list_case_claims(case_id=case_id, draft_id=draft_id, limit=500)
        data["review_items"] = self.list_review_items(
            case_id=case_id,
            status=None,
            item_type="draft",
            item_id=draft_id,
            limit=100,
        )
        return data

    def list_case_claims(
        self,
        *,
        case_id: str,
        pack_id: str | None = None,
        support_status: str | None = None,
        draft_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = ["lc.case_id = :case_id"]
        params: dict[str, Any] = {"case_id": case_id, "limit": limit}
        if pack_id is not None:
            conditions.append("lc.pack_id = :pack_id")
            params["pack_id"] = pack_id
        if support_status is not None:
            conditions.append("lc.support_status = :support_status")
            params["support_status"] = support_status
        if draft_id is not None:
            conditions.append("lc.metadata->>'draft_id' = :draft_id")
            params["draft_id"] = draft_id
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    lc.claim_id,
                    lc.case_id,
                    lc.thread_id,
                    lc.message_id,
                    lc.pack_id,
                    lc.claim_text,
                    lc.claim_type,
                    lc.support_status,
                    lc.risk_level,
                    (
                        SELECT count(*)
                        FROM legal_claim_citations lcc
                        WHERE lcc.claim_id = lc.claim_id
                    ) AS citation_count,
                    (
                        SELECT ri.status
                        FROM review_items ri
                        WHERE ri.case_id = lc.case_id
                          AND ri.item_type = 'legal_claim'
                          AND ri.item_id = lc.claim_id
                        ORDER BY ri.created_at DESC
                        LIMIT 1
                    ) AS review_status,
                    lc.created_by_agent_run_id,
                    lc.reviewed_by_user_id,
                    lc.reviewed_at,
                    lc.created_at,
                    lc.updated_at,
                    lc.metadata
                FROM legal_claims lc
                WHERE {' AND '.join(conditions)}
                ORDER BY lc.created_at DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        return [_claim_summary(row) for row in rows]

    def get_claim_detail(self, *, case_id: str, claim_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    lc.claim_id,
                    lc.case_id,
                    lc.thread_id,
                    lc.message_id,
                    lc.pack_id,
                    lc.claim_text,
                    lc.claim_type,
                    lc.support_status,
                    lc.risk_level,
                    (
                        SELECT count(*)
                        FROM legal_claim_citations lcc
                        WHERE lcc.claim_id = lc.claim_id
                    ) AS citation_count,
                    (
                        SELECT ri.status
                        FROM review_items ri
                        WHERE ri.case_id = lc.case_id
                          AND ri.item_type = 'legal_claim'
                          AND ri.item_id = lc.claim_id
                        ORDER BY ri.created_at DESC
                        LIMIT 1
                    ) AS review_status,
                    lc.created_by_agent_run_id,
                    lc.reviewed_by_user_id,
                    lc.reviewed_at,
                    lc.created_at,
                    lc.updated_at,
                    lc.metadata
                FROM legal_claims lc
                WHERE lc.case_id = :case_id
                  AND lc.claim_id = :claim_id
                """
            ),
            {"case_id": case_id, "claim_id": claim_id},
        ).mappings().first()
        if row is None:
            return None
        claim = _claim_summary(row)
        claim["citations"] = self._claim_citations(claim_id)
        claim["review_items"] = self.list_review_items(
            case_id=case_id,
            status=None,
            item_type="legal_claim",
            item_id=claim_id,
            limit=100,
        )
        return claim

    def _claim_citations(self, claim_id: str) -> list[dict[str, Any]]:
        rows = self.session.execute(
            text(
                """
                SELECT
                    lcc.pack_item_id,
                    lcc.citation_role,
                    rpi.pack_id,
                    rpi.chunk_id,
                    rc.document_id,
                    rc.title,
                    rc.document_type,
                    rc.source_id,
                    rc.authority_level,
                    rc.year,
                    rc.citation,
                    COALESCE(rpi.page_start, rc.page_start) AS page_start,
                    COALESCE(rpi.page_end, rc.page_end) AS page_end,
                    rc.source_url,
                    rc.local_path,
                    count(pia.anchor_id) FILTER (WHERE pia.status = 'active') AS anchor_count,
                    min(lcc.created_at) AS first_cited_at
                FROM legal_claim_citations lcc
                JOIN research_pack_items rpi ON rpi.pack_item_id = lcc.pack_item_id
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                LEFT JOIN pack_item_source_anchors pia ON pia.pack_item_id = lcc.pack_item_id
                WHERE lcc.claim_id = :claim_id
                GROUP BY
                    lcc.pack_item_id,
                    lcc.citation_role,
                    rpi.pack_id,
                    rpi.chunk_id,
                    rc.document_id,
                    rc.title,
                    rc.document_type,
                    rc.source_id,
                    rc.authority_level,
                    rc.year,
                    rc.citation,
                    COALESCE(rpi.page_start, rc.page_start),
                    COALESCE(rpi.page_end, rc.page_end),
                    rc.source_url,
                    rc.local_path
                ORDER BY first_cited_at ASC, lcc.pack_item_id ASC
                """
            ),
            {"claim_id": claim_id},
        ).mappings().all()
        citations: list[dict[str, Any]] = []
        for row in rows:
            item = _plain_dict(row)
            item.pop("first_cited_at", None)
            item["authority_level"] = int(item["authority_level"])
            item["year"] = int(item["year"]) if item["year"] is not None else None
            item["page_start"] = int(item["page_start"]) if item["page_start"] is not None else None
            item["page_end"] = int(item["page_end"]) if item["page_end"] is not None else None
            item["anchor_count"] = int(item["anchor_count"] or 0)
            item["source_endpoint"] = (
                f"/v1/research/packs/{item['pack_id']}/items/{item['pack_item_id']}/source"
            )
            citations.append(item)
        return citations

    def _pack_item_context(self, *, pack_id: str, pack_item_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    rpi.pack_item_id,
                    rpi.pack_id,
                    rpi.chunk_id,
                    rc.document_id,
                    rc.title,
                    rc.citation
                FROM research_pack_items rpi
                JOIN retrieval_chunks rc ON rc.chunk_id = rpi.chunk_id
                WHERE rpi.pack_id = :pack_id
                  AND rpi.pack_item_id = :pack_item_id
                """
            ),
            {"pack_id": pack_id, "pack_item_id": pack_item_id},
        ).mappings().first()
        return _plain_dict(row) if row is not None else None

    def _claim_state_for_metadata(self, *, case_id: str, claim_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    claim_id,
                    case_id,
                    pack_id,
                    claim_text,
                    support_status,
                    risk_level,
                    metadata
                FROM legal_claims
                WHERE case_id = :case_id
                  AND claim_id = :claim_id
                FOR UPDATE
                """
            ),
            {"case_id": case_id, "claim_id": claim_id},
        ).mappings().first()
        return _plain_dict(row) if row is not None else None

    def _store_evidence_assessment_metadata(
        self,
        *,
        case_id: str,
        claim_id: str,
        assessment: ClaimEvidenceAssessmentRequest,
        citation_role: str,
    ) -> None:
        claim = self._claim_state_for_metadata(case_id=case_id, claim_id=claim_id)
        if claim is None:
            raise ValueError(f"Claim not found for case: {claim_id}")
        metadata = dict(claim.get("metadata") or {})
        assessments = dict(metadata.get("evidence_assessments") or {})
        assessment_key = _evidence_assessment_key(
            pack_item_id=assessment.pack_item_id,
            citation_role=citation_role,
        )
        assessments[assessment_key] = {
            "schema_version": assessment.schema_version,
            "assessment_id": _evidence_assessment_id(
                claim_id=claim_id,
                pack_item_id=assessment.pack_item_id,
                citation_role=citation_role,
            ),
            "stance": assessment.stance.value,
            "citation_role": citation_role,
            "rationale": assessment.rationale,
            "confidence_score": assessment.confidence_score,
            "risk_level": assessment.risk_level,
            "source_quote": assessment.source_quote,
            "page_start": assessment.page_start,
            "page_end": assessment.page_end,
            "review_status": assessment.review_status,
            "metadata": assessment.metadata,
        }
        metadata["evidence_assessments"] = assessments
        self.session.execute(
            text(
                """
                UPDATE legal_claims
                SET
                    support_status = :support_status,
                    risk_level = :risk_level,
                    metadata = CAST(:metadata AS jsonb),
                    updated_at = now()
                WHERE case_id = :case_id
                  AND claim_id = :claim_id
                """
            ),
            {
                "case_id": case_id,
                "claim_id": claim_id,
                "support_status": _aggregate_support_status(assessments),
                "risk_level": _highest_risk_level(
                    [str(item.get("risk_level") or "medium") for item in assessments.values()]
                ),
                "metadata": _json(metadata),
            },
        )

    def _review_item_state_for_update(self, *, case_id: str, review_item_id: str) -> dict[str, Any] | None:
        row = self.session.execute(
            text(
                """
                SELECT
                    ri.review_item_id,
                    ri.case_id,
                    c.organization_id,
                    ri.item_type,
                    ri.item_id,
                    ri.status,
                    ri.priority,
                    ri.assigned_to_user_id,
                    ri.reviewed_by_user_id,
                    ri.decision,
                    ri.comment,
                    ri.due_at,
                    ri.reviewed_at,
                    ri.created_at,
                    ri.updated_at
                FROM review_items ri
                JOIN cases c ON c.case_id = ri.case_id
                WHERE ri.case_id = :case_id
                  AND ri.review_item_id = :review_item_id
                FOR UPDATE OF ri
                """
            ),
            {"case_id": case_id, "review_item_id": review_item_id},
        ).mappings().first()
        return _plain_dict(row) if row is not None else None

    def _review_target_state(self, *, case_id: str, item_type: str, item_id: str) -> dict[str, Any] | None:
        if item_type in {"draft", "adverse_evidence", "missing_evidence"}:
            row = self.session.execute(
                text(
                    """
                    SELECT
                        draft_id,
                        case_id,
                        thread_id,
                        pack_id,
                        draft_type,
                        title,
                        status,
                        version,
                        created_by_agent_run_id,
                        created_by_user_id,
                        metadata,
                        created_at,
                        updated_at
                    FROM drafts
                    WHERE case_id = :case_id
                      AND draft_id = :item_id
                    """
                ),
                {"case_id": case_id, "item_id": item_id},
            ).mappings().first()
            return _plain_dict(row) if row is not None else None
        if item_type == "legal_claim":
            row = self.session.execute(
                text(
                    """
                    SELECT
                        claim_id,
                        case_id,
                        thread_id,
                        message_id,
                        pack_id,
                        claim_text,
                        claim_type,
                        support_status,
                        risk_level,
                        created_by_agent_run_id,
                        reviewed_by_user_id,
                        reviewed_at,
                        metadata,
                        created_at,
                        updated_at
                    FROM legal_claims
                    WHERE case_id = :case_id
                      AND claim_id = :item_id
                    """
                ),
                {"case_id": case_id, "item_id": item_id},
            ).mappings().first()
            return _plain_dict(row) if row is not None else None
        return None

    def _insert_audit_event(
        self,
        *,
        organization_id: str | None,
        case_id: str | None,
        user_id: str | None,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        audit_event_id = self.session.execute(
            text(
                """
                INSERT INTO audit_events (
                    organization_id, case_id, user_id, event_type, entity_type,
                    entity_id, before_state, after_state, metadata
                )
                VALUES (
                    :organization_id, :case_id, :user_id, :event_type, :entity_type,
                    :entity_id, CAST(:before_state AS jsonb), CAST(:after_state AS jsonb),
                    CAST(:metadata AS jsonb)
                )
                RETURNING audit_event_id
                """
            ),
            {
                "organization_id": organization_id,
                "case_id": case_id,
                "user_id": user_id,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "before_state": _json(before_state or {}),
                "after_state": _json(after_state or {}),
                "metadata": _json(metadata or {}),
            },
        ).scalar_one()
        return int(audit_event_id)

    def record_audit_event(
        self,
        *,
        organization_id: str | None,
        case_id: str | None,
        user_id: str | None,
        event_type: str,
        entity_type: str,
        entity_id: str | None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        audit_event_id = self._insert_audit_event(
            organization_id=organization_id,
            case_id=case_id,
            user_id=user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
            after_state=after_state,
            metadata=metadata,
        )
        self.session.flush()
        return audit_event_id

    def list_audit_events(
        self,
        *,
        organization_id: str,
        user_id: str | None = None,
        case_id: str | None = None,
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        before_created_at: datetime | None = None,
        before_audit_event_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = ["organization_id = :organization_id"]
        params: dict[str, Any] = {"organization_id": organization_id, "limit": limit}
        if user_id is not None:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        if case_id is not None:
            conditions.append("case_id = :case_id")
            params["case_id"] = case_id
        if event_type is not None:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type
        if entity_type is not None:
            conditions.append("entity_type = :entity_type")
            params["entity_type"] = entity_type
        if entity_id is not None:
            conditions.append("entity_id = :entity_id")
            params["entity_id"] = entity_id
        if before_created_at is not None and before_audit_event_id is not None:
            conditions.append("(created_at, audit_event_id) < (:before_created_at, :before_audit_event_id)")
            params["before_created_at"] = before_created_at
            params["before_audit_event_id"] = before_audit_event_id
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    audit_event_id,
                    organization_id,
                    case_id,
                    user_id,
                    event_type,
                    entity_type,
                    entity_id,
                    before_state,
                    after_state,
                    metadata,
                    ip_address,
                    user_agent,
                    created_at
                FROM audit_events
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC, audit_event_id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        events: list[dict[str, Any]] = []
        for row in rows:
            item = _plain_dict(row)
            item["audit_event_id"] = int(item["audit_event_id"])
            item["before_state"] = dict(item["before_state"]) if item["before_state"] is not None else None
            item["after_state"] = dict(item["after_state"]) if item["after_state"] is not None else None
            item["metadata"] = dict(item["metadata"] or {})
            events.append(item)
        return events

    def list_case_audit_events(
        self,
        *,
        case_id: str,
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        before_created_at: datetime | None = None,
        before_audit_event_id: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conditions = ["case_id = :case_id"]
        params: dict[str, Any] = {"case_id": case_id, "limit": limit}
        if event_type is not None:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type
        if entity_type is not None:
            conditions.append("entity_type = :entity_type")
            params["entity_type"] = entity_type
        if entity_id is not None:
            conditions.append("entity_id = :entity_id")
            params["entity_id"] = entity_id
        if before_created_at is not None and before_audit_event_id is not None:
            conditions.append("(created_at, audit_event_id) < (:before_created_at, :before_audit_event_id)")
            params["before_created_at"] = before_created_at
            params["before_audit_event_id"] = before_audit_event_id
        rows = self.session.execute(
            text(
                f"""
                SELECT
                    audit_event_id,
                    organization_id,
                    case_id,
                    user_id,
                    event_type,
                    entity_type,
                    entity_id,
                    before_state,
                    after_state,
                    metadata,
                    ip_address,
                    user_agent,
                    created_at
                FROM audit_events
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC, audit_event_id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        events: list[dict[str, Any]] = []
        for row in rows:
            item = _plain_dict(row)
            item["audit_event_id"] = int(item["audit_event_id"])
            item["before_state"] = dict(item["before_state"]) if item["before_state"] is not None else None
            item["after_state"] = dict(item["after_state"]) if item["after_state"] is not None else None
            item["metadata"] = dict(item["metadata"] or {})
            events.append(item)
        return events

    def case_overview(self, case_id: str) -> dict[str, int | str]:
        row = self.session.execute(
            text(
                """
                SELECT
                    c.case_id,
                    c.title,
                    (SELECT count(*) FROM case_facts cf WHERE cf.case_id = c.case_id) AS fact_count,
                    (SELECT count(*) FROM case_issues ci WHERE ci.case_id = c.case_id) AS issue_count,
                    (SELECT count(*) FROM chat_threads ct WHERE ct.case_id = c.case_id) AS thread_count,
                    (SELECT count(*) FROM case_research_packs crp WHERE crp.case_id = c.case_id) AS pack_count,
                    (SELECT count(*) FROM legal_claims lc WHERE lc.case_id = c.case_id) AS claim_count,
                    (SELECT count(*) FROM review_items ri WHERE ri.case_id = c.case_id) AS review_count
                FROM cases c
                WHERE c.case_id = :case_id
                """
            ),
            {"case_id": case_id},
        ).mappings().one()
        return dict(row)


def research_pack_hash(pack: LegalResearchPack) -> str:
    return canonical_research_pack_hash(pack)


def _agentic_research_metadata(
    *,
    agentic_research_plan: AgentResearchPlan | None,
    matter_memory: MatterMemory | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if agentic_research_plan is not None:
        metadata["agentic_research_plan"] = agentic_research_plan.model_dump(mode="json")
    if matter_memory is not None:
        metadata["matter_memory"] = matter_memory.model_dump(mode="json")
    return metadata


def _plain_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _draft_summary(row: Any) -> dict[str, Any]:
    data = _plain_dict(row)
    data["version"] = int(data["version"])
    data["claim_count"] = int(data["claim_count"] or 0)
    data["metadata"] = dict(data["metadata"] or {})
    data["content_preview"] = str(data["content_preview"] or "")
    return data


def _claim_summary(row: Any) -> dict[str, Any]:
    data = _plain_dict(row)
    data["citation_count"] = int(data["citation_count"] or 0)
    data["metadata"] = dict(data["metadata"] or {})
    return data


def _evidence_assessment(row: Any) -> dict[str, Any]:
    data = _plain_dict(row)
    citation_role = str(data["citation_role"])
    stance = evidence_stance_for_citation_role(citation_role)
    metadata = dict(data.get("claim_metadata") or {})
    details = dict(
        (metadata.get("evidence_assessments") or {}).get(
            _evidence_assessment_key(pack_item_id=str(data["pack_item_id"]), citation_role=citation_role),
            {},
        )
    )
    page_start = details.get("page_start", data.get("page_start"))
    page_end = details.get("page_end", data.get("page_end"))
    assessment = {
        "schema_version": str(details.get("schema_version") or "claim_evidence_assessment.v1"),
        "assessment_id": str(
            details.get("assessment_id")
            or _evidence_assessment_id(
                claim_id=str(data["claim_id"]),
                pack_item_id=str(data["pack_item_id"]),
                citation_role=citation_role,
            )
        ),
        "case_id": str(data["case_id"]),
        "claim_id": str(data["claim_id"]),
        "claim_text": str(data["claim_text"]),
        "pack_id": str(data["pack_id"]),
        "pack_item_id": str(data["pack_item_id"]),
        "stance": stance.value,
        "citation_role": citation_role,
        "rationale": str(details.get("rationale") or "Assessment rationale not yet recorded."),
        "confidence_score": float(details.get("confidence_score", 0.0)),
        "risk_level": str(details.get("risk_level") or data.get("risk_level") or "medium"),
        "source_quote": str(details.get("source_quote") or data.get("selected_text") or ""),
        "page_start": int(page_start) if page_start is not None else None,
        "page_end": int(page_end) if page_end is not None else None,
        "review_status": str(details.get("review_status") or data.get("review_status") or "pending"),
        "document_id": str(data["document_id"]),
        "title": str(data["title"]),
        "document_type": str(data["document_type"]),
        "source_id": str(data["source_id"]),
        "authority_level": int(data["authority_level"]),
        "year": int(data["year"]) if data.get("year") is not None else None,
        "citation": str(data["citation"]),
        "source_url": str(data["source_url"]) if data.get("source_url") else None,
        "local_path": str(data["local_path"]) if data.get("local_path") else None,
        "anchor_count": int(data.get("anchor_count") or 0),
        "source_endpoint": f"/v1/research/packs/{data['pack_id']}/items/{data['pack_item_id']}/source",
        "metadata": dict(details.get("metadata") or {}),
    }
    return ClaimEvidenceAssessment.model_validate(assessment).model_dump(mode="json")


def _evidence_assessment_key(*, pack_item_id: str, citation_role: str) -> str:
    return f"{pack_item_id}:{citation_role}"


def _evidence_assessment_id(*, claim_id: str, pack_item_id: str, citation_role: str) -> str:
    digest = hashlib.sha256(f"{claim_id}:{pack_item_id}:{citation_role}".encode("utf-8")).hexdigest()
    return f"assess_{digest[:32]}"


def _support_status_for_stance(stance: EvidenceStance | str) -> str:
    normalized = _normalize_evidence_stance(stance)
    return {
        EvidenceStance.SUPPORTS_CLAIM: "supported",
        EvidenceStance.CONTRADICTS_CLAIM: "adverse",
        EvidenceStance.MIXED: "mixed",
        EvidenceStance.CONTEXT: "context",
    }[normalized]


def _evidence_stance_value(stance: EvidenceStance | str | None) -> str | None:
    if stance is None:
        return None
    return _normalize_evidence_stance(stance).value


def _normalize_evidence_stance(stance: EvidenceStance | str) -> EvidenceStance:
    if isinstance(stance, EvidenceStance):
        return stance
    return EvidenceStance(str(stance))


def _aggregate_support_status(assessments: dict[str, Any]) -> str:
    stances = {
        str(item.get("stance"))
        for item in assessments.values()
        if isinstance(item, dict) and item.get("stance")
    }
    if EvidenceStance.MIXED.value in stances or len(stances.intersection({
        EvidenceStance.SUPPORTS_CLAIM.value,
        EvidenceStance.CONTRADICTS_CLAIM.value,
    })) > 1:
        return "mixed"
    if EvidenceStance.CONTRADICTS_CLAIM.value in stances:
        return "adverse"
    if EvidenceStance.SUPPORTS_CLAIM.value in stances:
        return "supported"
    if EvidenceStance.CONTEXT.value in stances:
        return "context"
    return "unverified"


def _highest_risk_level(values: Iterable[str]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    ranked = [value for value in values if value in order]
    if not ranked:
        return "medium"
    return max(ranked, key=lambda value: order[value])


def _case_document_file_context(*, case_id: str, row: Any) -> dict[str, Any]:
    data = _plain_dict(row)
    document_id = str(data["document_id"])
    title = str(data.get("title") or "Untitled legal document")
    local_path = str(data["local_path"]) if data.get("local_path") else None
    source_url = str(data["source_url"]) if data.get("source_url") else None
    download_url = str(data["download_url"]) if data.get("download_url") else None
    absolute_local_path, local_file_exists = resolve_local_path(local_path)
    case_file_name = _case_document_filename(
        document_id=document_id,
        title=title,
        local_path=local_path,
        source_url=download_url or source_url,
    )
    case_file_path = _case_file_cache_root() / _safe_path_segment(case_id) / case_file_name
    case_file_exists = case_file_path.is_file()
    effective_path = case_file_path if case_file_exists else Path(absolute_local_path) if absolute_local_path and local_file_exists else None
    case_file_available = bool(effective_path and effective_path.is_file())
    return {
        "document_id": document_id,
        "title": title,
        "document_type": str(data.get("document_type") or "legal_document"),
        "local_path": local_path,
        "source_url": source_url,
        "download_url": download_url,
        "file_hash": str(data["file_hash"]) if data.get("file_hash") else None,
        "absolute_local_path": str(Path(absolute_local_path)) if absolute_local_path else None,
        "local_file_exists": bool(absolute_local_path and local_file_exists and Path(absolute_local_path).is_file()),
        "case_file_path": str(case_file_path),
        "case_file_available": case_file_available,
        "case_file_name": case_file_name,
        "effective_file_path": str(effective_path) if effective_path else None,
        "viewer_mime_type": _mime_type_for_filename(case_file_name),
    }


def _workspace_document(row: Any) -> dict[str, Any]:
    data = _plain_dict(row)
    title = str(data.get("title") or "Untitled legal document")
    file_context = _case_document_file_context(case_id=str(data["case_id"]), row=data) if data.get("case_id") else None
    return {
        "documentId": str(data["document_id"]),
        "title": title,
        "documentType": str(data.get("document_type") or "legal_document"),
        "citation": str(data.get("citation") or title),
        "sourceId": str(data.get("source_id") or "unknown_source"),
        "authorityLevel": int(data.get("authority_level") or 99),
        "pageCount": _workspace_document_page_count(data),
        "qualityFlags": _dedupe(_text_list(data.get("quality_flags"))),
        "textPreview": str(data.get("text_preview") or ""),
        "localPath": str(data["local_path"]) if data.get("local_path") else None,
        "sourceUrl": str(data["source_url"]) if data.get("source_url") else None,
        "downloadUrl": str(data["download_url"]) if data.get("download_url") else None,
        "caseFileAvailable": bool(file_context and file_context["case_file_available"]),
        "caseFileName": str(file_context["case_file_name"]) if file_context else None,
        "viewerMimeType": str(file_context["viewer_mime_type"]) if file_context else None,
        "relevanceScore": _optional_float(data.get("relevance_score")),
        "confidenceScore": _optional_float(data.get("confidence_score")),
        "relevanceBand": str(data["relevance_band"]) if data.get("relevance_band") else None,
        "relevanceRationale": str(data["relevance_rationale"]) if data.get("relevance_rationale") else None,
    }


def _stable_relevance_id(*, case_id: str, document_id: str, source: str) -> str:
    digest = hashlib.sha256(f"{case_id}:{document_id}:{source}".encode("utf-8")).hexdigest()
    return f"rel_{digest[:32]}"


def _relevance_band(score: float) -> str:
    if score >= 0.95:
        return "direct"
    if score >= 0.75:
        return "strong"
    if score >= 0.45:
        return "moderate"
    if score >= 0.10:
        return "weak"
    if score > 0:
        return "background"
    return "irrelevant"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _workspace_document_page_count(data: dict[str, Any]) -> int:
    page_count = int(data.get("page_count") or 0)
    if page_count:
        return page_count
    notes = str(data.get("document_notes") or "")
    match = re.search(r"(?:^|[;\s])pages=(\d+)(?:$|[;\s])", notes)
    return int(match.group(1)) if match else 0


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value if item]


def _target_status_for_decision(item_type: str, decision: str) -> str:
    if item_type in {"draft", "adverse_evidence", "missing_evidence"}:
        return {
            "approved": "approved",
            "rejected": "rejected",
            "changes_requested": "changes_requested",
        }[decision]
    if item_type == "legal_claim":
        return {
            "approved": "lawyer_approved",
            "rejected": "rejected",
            "changes_requested": "changes_requested",
        }[decision]
    raise ValueError(f"Unsupported review item type: {item_type}")


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _draft_title(requested_output: str, pack: LegalResearchPack) -> str:
    label = requested_output.replace("_", " ").strip().title() or "Strategy Draft"
    return f"{label} from {pack.pack_id}"


def _chat_thread_title(content: str) -> str:
    compact = " ".join(content.split())
    if len(compact) <= 80:
        return compact or "Case chat"
    return f"{compact[:77]}..."


def _sha256(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


def resolve_local_path(local_path: str | None) -> tuple[str | None, bool]:
    if not local_path:
        return None, False
    path = Path(local_path)
    absolute = path if path.is_absolute() else PROJECT_ROOT / path
    return str(absolute), absolute.exists()


def _case_file_cache_root() -> Path:
    configured = os.getenv(CASE_FILE_CACHE_ROOT_ENV)
    root = Path(configured).expanduser() if configured else PROJECT_ROOT / "data" / "case_files"
    return root if root.is_absolute() else PROJECT_ROOT / root


def _case_file_cache_max_bytes() -> int:
    return _positive_int_env(CASE_FILE_CACHE_MAX_BYTES_ENV, DEFAULT_CASE_FILE_CACHE_MAX_BYTES)


def _case_file_cache_timeout_seconds() -> int:
    return _positive_int_env(CASE_FILE_CACHE_TIMEOUT_SECONDS_ENV, DEFAULT_CASE_FILE_CACHE_TIMEOUT_SECONDS)


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1") from None
    return value


def _case_document_filename(*, document_id: str, title: str, local_path: str | None, source_url: str | None) -> str:
    suffix = _case_document_suffix(local_path=local_path, source_url=source_url)
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._-")
    compact_title = safe_title[:96] if safe_title else "legal_document"
    safe_id = _safe_path_segment(document_id)[:48]
    return f"{safe_id}_{compact_title}{suffix}"


def _case_document_suffix(*, local_path: str | None, source_url: str | None) -> str:
    if local_path:
        suffix = Path(local_path).suffix
        if suffix:
            return suffix[:16].lower()
    if source_url:
        parsed = urllib.parse.urlparse(source_url)
        suffix = Path(urllib.parse.unquote(parsed.path)).suffix
        if suffix:
            return suffix[:16].lower()
    return ".bin"


def _safe_path_segment(value: str) -> str:
    safe_value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe_value or "item"


def _mime_type_for_filename(filename: str) -> str:
    mime_type, _encoding = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def _copy_case_file(*, source_path: Path, cached_path: Path) -> None:
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f"{cached_path.name}.", suffix=".part", dir=cached_path.parent, delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        shutil.copy2(source_path, temp_path)
        temp_path.replace(cached_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _download_case_file(*, source_url: str, cached_path: Path) -> None:
    _validate_remote_document_url(source_url)
    max_bytes = _case_file_cache_max_bytes()
    timeout_seconds = _case_file_cache_timeout_seconds()
    request = urllib.request.Request(source_url, headers={"User-Agent": "SL-Legal-Assist/1.0"})
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(_SafeDocumentRedirectHandler)
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            declared_size = response.headers.get("Content-Length")
            if declared_size is not None and int(declared_size) > max_bytes:
                raise ValueError(f"Document source exceeds {max_bytes} bytes")
            with tempfile.NamedTemporaryFile(prefix=f"{cached_path.name}.", suffix=".part", dir=cached_path.parent, delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                bytes_written = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise ValueError(f"Document source exceeds {max_bytes} bytes")
                    temp_file.write(chunk)
            temp_path.replace(cached_path)
    except urllib.error.URLError as exc:
        raise FileNotFoundError(f"Unable to cache document from source URL: {source_url}") from exc
    finally:
        if "temp_path" in locals():
            temp_path.unlink(missing_ok=True)


class _SafeDocumentRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _validate_remote_document_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_remote_document_url(source_url: str) -> None:
    parsed = urllib.parse.urlparse(source_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Document caching supports only HTTP and HTTPS source URLs")
    if parsed.username or parsed.password:
        raise ValueError("Document source URL must not include credentials")
    if not parsed.hostname:
        raise ValueError("Document source URL must include a hostname")
    hostname = parsed.hostname.rstrip(".").lower()
    allowed_hosts = _remote_document_allowed_hosts()
    if allowed_hosts and not any(_host_matches_allowed_pattern(hostname, allowed) for allowed in allowed_hosts):
        raise ValueError(f"Document source host is not allowlisted: {hostname}")
    _reject_private_or_local_hostname(hostname, parsed.port)


def _remote_document_allowed_hosts() -> list[str]:
    raw_value = os.getenv(CASE_FILE_CACHE_ALLOWED_HOSTS_ENV, "")
    return [item.strip().lower().lstrip(".") for item in raw_value.split(",") if item.strip()]


def _host_matches_allowed_pattern(hostname: str, allowed: str) -> bool:
    return hostname == allowed or hostname.endswith(f".{allowed}")


def _reject_private_or_local_hostname(hostname: str, port: int | None) -> None:
    try:
        parsed_ip = ipaddress.ip_address(hostname)
        addresses = [parsed_ip]
    except ValueError:
        try:
            resolved = socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError(f"Document source host could not be resolved: {hostname}") from exc
        addresses = []
        for item in resolved:
            sockaddr = item[4]
            if not sockaddr:
                continue
            addresses.append(ipaddress.ip_address(str(sockaddr[0])))
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError(f"Document source host resolves to a blocked network address: {hostname}")


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def _json_value(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _sorted_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in sorted(payload)}


def _ocr_confidence_band(text_quality_score: float | None) -> str | None:
    if text_quality_score is None:
        return None
    if text_quality_score >= 0.95:
        return "high"
    if text_quality_score >= 0.80:
        return "medium"
    return "low"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
