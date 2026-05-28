from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.responses import Response

from .auth import (
    BODY_SHA256_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    USER_HEADER,
    AuthContext,
    authenticate_auth_headers,
    optional_auth_context,
    require_auth_context,
)
from .case_structure import generate_case_structure
from .db import LegalWorkspaceRepository, session_scope
from .db.repositories import RateLimitResult, research_pack_hash
from .hybrid_retrieval import RetrievalServiceError, create_research_pack
from .llm import AzureChatClient, load_azure_chat_config
from .metrics import METRICS, monotonic_ms, render_prometheus_text
from .models import (
    AuditEventListResponse,
    AuditEventStreamResponse,
    CaseWorkspaceSnapshot,
    CaseStructureRequest,
    ClaimEvidenceAssessmentRequest,
    ClaimDetail,
    ClaimListResponse,
    DraftDetail,
    DraftListResponse,
    EvidenceAssessmentCreateResponse,
    EvidenceAssessmentGroupedResponse,
    EvidenceStance,
    LegalResearchPack,
    PersistedStrategyDraftResponse,
    ResearchPackExpansionRequest,
    ResearchQueryRequest,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueResponse,
    StrategyDraftRequest,
    StrategyDraftResponse,
    WorkspaceCaseCreateRequest,
    WorkspaceCaseCreateResponse,
    WorkspaceChatMessage,
    WorkspaceChatMessageCreateRequest,
    WorkspaceChatMessageCreateResponse,
    WorkspaceDocument,
    WorkspaceDocumentPageResponse,
    WorkspaceDocumentFileResponse,
)
from .research_pack import seal_research_pack
from .strategy import build_strategy_prompt, extract_pack_item_references, generate_strategy_draft


@dataclass(frozen=True)
class RateLimitPolicy:
    route_key: str
    limit: int
    window_seconds: int


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1")
    return value


RATE_LIMIT_WINDOW_SECONDS = _int_env("SL_LEGAL_RATE_LIMIT_WINDOW_SECONDS", 3600)
RESEARCH_PACK_RATE_LIMIT = RateLimitPolicy(
    route_key="research_pack.create",
    limit=_int_env("SL_LEGAL_RESEARCH_PACK_RATE_LIMIT", 60),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
RESEARCH_PACK_EXPAND_RATE_LIMIT = RateLimitPolicy(
    route_key="research_pack.expand",
    limit=_int_env("SL_LEGAL_RESEARCH_PACK_EXPAND_RATE_LIMIT", 60),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
STRATEGY_PROMPT_RATE_LIMIT = RateLimitPolicy(
    route_key="strategy.prompt",
    limit=_int_env("SL_LEGAL_STRATEGY_PROMPT_RATE_LIMIT", 120),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
CASE_STRUCTURE_RATE_LIMIT = RateLimitPolicy(
    route_key="case.structure",
    limit=_int_env("SL_LEGAL_CASE_STRUCTURE_RATE_LIMIT", 30),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
STRATEGY_DRAFT_RATE_LIMIT = RateLimitPolicy(
    route_key="strategy.draft",
    limit=_int_env("SL_LEGAL_STRATEGY_DRAFT_RATE_LIMIT", 30),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
STRATEGY_VALIDATE_RATE_LIMIT = RateLimitPolicy(
    route_key="strategy.validate",
    limit=_int_env("SL_LEGAL_STRATEGY_VALIDATE_RATE_LIMIT", 120),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
UI_CASE_CREATE_RATE_LIMIT = RateLimitPolicy(
    route_key="ui.case.create",
    limit=_int_env("SL_LEGAL_UI_CASE_CREATE_RATE_LIMIT", 30),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
UI_CHAT_MESSAGE_RATE_LIMIT = RateLimitPolicy(
    route_key="ui.chat.message",
    limit=_int_env("SL_LEGAL_UI_CHAT_MESSAGE_RATE_LIMIT", 120),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
UI_DOCUMENT_CACHE_RATE_LIMIT = RateLimitPolicy(
    route_key="ui.document.cache",
    limit=_int_env("SL_LEGAL_UI_DOCUMENT_CACHE_RATE_LIMIT", 300),
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)
UI_CHAT_RESEARCH_MAX_PACK_ITEMS = _int_env("SL_LEGAL_UI_CHAT_RESEARCH_MAX_PACK_ITEMS", 8)
UI_CHAT_RESEARCH_MAX_PACK_TOKENS = _int_env("SL_LEGAL_UI_CHAT_RESEARCH_MAX_PACK_TOKENS", 8000)

RESEARCH_PACK_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_RESEARCH_PACK_BODY_LIMIT_BYTES", 64 * 1024)
STRATEGY_PROMPT_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_STRATEGY_PROMPT_BODY_LIMIT_BYTES", 2 * 1024 * 1024)
CASE_STRUCTURE_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_CASE_STRUCTURE_BODY_LIMIT_BYTES", 512 * 1024)
STRATEGY_DRAFT_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_STRATEGY_DRAFT_BODY_LIMIT_BYTES", 2 * 1024 * 1024)
STRATEGY_VALIDATE_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_STRATEGY_VALIDATE_BODY_LIMIT_BYTES", 1024 * 1024)
EVIDENCE_ASSESSMENT_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_EVIDENCE_ASSESSMENT_BODY_LIMIT_BYTES", 256 * 1024)
UI_CASE_CREATE_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_UI_CASE_CREATE_BODY_LIMIT_BYTES", 32 * 1024)
UI_CHAT_MESSAGE_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_UI_CHAT_MESSAGE_BODY_LIMIT_BYTES", 64 * 1024)
UI_DOCUMENT_CACHE_BODY_LIMIT_BYTES = _int_env("SL_LEGAL_UI_DOCUMENT_CACHE_BODY_LIMIT_BYTES", 4 * 1024)
METRICS_BEARER_TOKEN_ENV = "SL_LEGAL_METRICS_BEARER_TOKEN"
MIN_METRICS_BEARER_TOKEN_LENGTH = 32


def _request_body_limit_dependency(route_key: str, max_bytes: int):
    async def dependency(request: Request) -> None:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Content-Length header is invalid") from exc
            if declared_size > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request body for {route_key} exceeds {max_bytes} bytes",
                )
        body = await request.body()
        if len(body) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Request body for {route_key} exceeds {max_bytes} bytes",
            )

    return dependency


RESEARCH_PACK_BODY_LIMIT = _request_body_limit_dependency("research_pack.create", RESEARCH_PACK_BODY_LIMIT_BYTES)
STRATEGY_PROMPT_BODY_LIMIT = _request_body_limit_dependency("strategy.prompt", STRATEGY_PROMPT_BODY_LIMIT_BYTES)
CASE_STRUCTURE_BODY_LIMIT = _request_body_limit_dependency("case.structure", CASE_STRUCTURE_BODY_LIMIT_BYTES)
STRATEGY_DRAFT_BODY_LIMIT = _request_body_limit_dependency("strategy.draft", STRATEGY_DRAFT_BODY_LIMIT_BYTES)
STRATEGY_VALIDATE_BODY_LIMIT = _request_body_limit_dependency("strategy.validate", STRATEGY_VALIDATE_BODY_LIMIT_BYTES)
EVIDENCE_ASSESSMENT_BODY_LIMIT = _request_body_limit_dependency(
    "evidence.assessment",
    EVIDENCE_ASSESSMENT_BODY_LIMIT_BYTES,
)
UI_CASE_CREATE_BODY_LIMIT = _request_body_limit_dependency("ui.case.create", UI_CASE_CREATE_BODY_LIMIT_BYTES)
UI_CHAT_MESSAGE_BODY_LIMIT = _request_body_limit_dependency("ui.chat.message", UI_CHAT_MESSAGE_BODY_LIMIT_BYTES)
UI_DOCUMENT_CACHE_BODY_LIMIT = _request_body_limit_dependency("ui.document.cache", UI_DOCUMENT_CACHE_BODY_LIMIT_BYTES)

SIGNED_POST_BODY_LIMITS = {
    "/v1/research/packs": ("research_pack.create", RESEARCH_PACK_BODY_LIMIT_BYTES),
    "/v1/strategy/prompt": ("strategy.prompt", STRATEGY_PROMPT_BODY_LIMIT_BYTES),
    "/v1/cases/structure": ("case.structure", CASE_STRUCTURE_BODY_LIMIT_BYTES),
    "/v1/strategy/draft": ("strategy.draft", STRATEGY_DRAFT_BODY_LIMIT_BYTES),
    "/v1/strategy/validate": ("strategy.validate", STRATEGY_VALIDATE_BODY_LIMIT_BYTES),
    "/v1/cases/{case_id}/evidence/assessments": (
        "evidence.assessment",
        EVIDENCE_ASSESSMENT_BODY_LIMIT_BYTES,
    ),
    "/v1/ui/cases": ("ui.case.create", UI_CASE_CREATE_BODY_LIMIT_BYTES),
}


async def _require_operations_metrics_access(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_sl_legal_user_id: str | None = Header(default=None, alias=USER_HEADER),
    x_sl_legal_auth_timestamp: str | None = Header(default=None, alias=TIMESTAMP_HEADER),
    x_sl_legal_auth_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    x_sl_legal_body_sha256: str | None = Header(default=None, alias=BODY_SHA256_HEADER),
) -> None:
    if authorization:
        _require_metrics_bearer_token(authorization)
        return

    auth = await optional_auth_context(
        request=request,
        x_sl_legal_user_id=x_sl_legal_user_id,
        x_sl_legal_auth_timestamp=x_sl_legal_auth_timestamp,
        x_sl_legal_auth_signature=x_sl_legal_auth_signature,
        x_sl_legal_body_sha256=x_sl_legal_body_sha256,
    )
    if auth is None:
        raise HTTPException(status_code=401, detail="Metrics authentication is required")
    with session_scope() as session:
        _require_active_user(LegalWorkspaceRepository(session), auth.user_id)


def _require_metrics_bearer_token(authorization: str) -> None:
    scheme, _, token = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Metrics bearer token is invalid")
    expected_token = os.getenv(METRICS_BEARER_TOKEN_ENV, "")
    if len(expected_token) < MIN_METRICS_BEARER_TOKEN_LENGTH:
        raise HTTPException(
            status_code=500,
            detail=f"{METRICS_BEARER_TOKEN_ENV} must be set to at least {MIN_METRICS_BEARER_TOKEN_LENGTH} characters",
        )
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail="Metrics bearer token is invalid")


app = FastAPI(title="SL Legal Assist RAG API", version="0.1.0")


@app.middleware("http")
async def operational_metrics_middleware(request: Request, call_next):
    started_ms = monotonic_ms()
    response: Response | None = None
    try:
        body_limit = SIGNED_POST_BODY_LIMITS.get(request.url.path)
        if request.method.upper() == "POST" and body_limit is not None:
            route_key, max_bytes = body_limit
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    response = JSONResponse(status_code=400, content={"detail": "Content-Length header is invalid"})
                    return response
                if declared_size > max_bytes:
                    _record_oversized_request_if_signed(
                        request=request,
                        route_key=route_key,
                        max_bytes=max_bytes,
                        declared_size=declared_size,
                    )
                    METRICS.increment("guardrail_request_body_too_large_total", route_key=route_key)
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": f"Request body for {route_key} exceeds {max_bytes} bytes"},
                    )
                    return response
        response = await call_next(request)
        return response
    finally:
        duration_ms = monotonic_ms() - started_ms
        status_code = response.status_code if response is not None else 500
        route_label = _route_metric_label(request)
        method = request.method.upper()
        status_class = f"{status_code // 100}xx"
        METRICS.increment(
            "http_requests_total",
            route=route_label,
            method=method,
            status_code=status_code,
            status_class=status_class,
        )
        if status_code >= 400:
            METRICS.increment(
                "http_request_errors_total",
                route=route_label,
                method=method,
                status_code=status_code,
                status_class=status_class,
            )
        METRICS.observe_latency(duration_ms, route=route_label, method=method)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/operations/metrics")
async def operations_metrics(_: None = Depends(_require_operations_metrics_access)) -> dict[str, Any]:
    return METRICS.snapshot()


@app.get("/v1/operations/metrics/prometheus")
async def operations_metrics_prometheus(_: None = Depends(_require_operations_metrics_access)) -> PlainTextResponse:
    return PlainTextResponse(
        render_prometheus_text(METRICS.snapshot()),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.post("/v1/research/packs")
def create_research_pack_endpoint(
    request: ResearchQueryRequest,
    _body_size: None = Depends(RESEARCH_PACK_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    return _create_research_pack_response(request=request, auth=auth, rate_limit_policy=RESEARCH_PACK_RATE_LIMIT)


@app.post("/v1/research/packs/{pack_id}/expand")
def expand_research_pack_endpoint(
    pack_id: str,
    request: ResearchPackExpansionRequest,
    _body_size: None = Depends(RESEARCH_PACK_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        parent_case_id = _require_research_pack_access_permission(repo, pack_id=pack_id, user_id=auth.user_id)
    research_request = request.to_research_query_request(parent_pack_id=pack_id, case_id=parent_case_id)
    return _create_research_pack_response(
        request=research_request,
        auth=auth,
        rate_limit_policy=RESEARCH_PACK_EXPAND_RATE_LIMIT,
    )


def _create_research_pack_response(
    *,
    request: ResearchQueryRequest,
    auth: AuthContext,
    rate_limit_policy: RateLimitPolicy,
) -> dict[str, object]:
    rate_limit_result = None
    try:
        organization_id: str | None = None
        effective_case_id = request.case_id
        pack_version = 1
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            parent_case_id: str | None = None
            if request.parent_pack_id is not None:
                parent_case_id = _require_research_pack_access_permission(
                    repo,
                    pack_id=request.parent_pack_id,
                    user_id=auth.user_id,
                )
                pack_version = repo.next_child_research_pack_version(request.parent_pack_id)
                if effective_case_id is None:
                    effective_case_id = parent_case_id
                elif parent_case_id is not None and effective_case_id != parent_case_id:
                    raise HTTPException(status_code=403, detail="Expanded research pack must stay within the parent pack case")
            if effective_case_id is not None:
                case_context = _require_case_permission(
                    repo,
                    case_id=effective_case_id,
                    user_id=auth.user_id,
                )
                organization_id = case_context.organization_id
            else:
                organization_id = _require_active_user(repo, auth.user_id).organization_id
            rate_limit_result = _consume_rate_limit(
                repo,
                organization_id=organization_id,
                user_id=auth.user_id,
                policy=rate_limit_policy,
            )
            if not rate_limit_result.allowed:
                _record_rate_limit_rejection(
                    repo,
                    organization_id=organization_id,
                    case_id=effective_case_id,
                    user_id=auth.user_id,
                    result=rate_limit_result,
                )
        if rate_limit_result is not None and not rate_limit_result.allowed:
            _raise_rate_limit_exceeded(rate_limit_result)
        retrieval_request = request.model_copy(update={"case_id": effective_case_id})
        pack = seal_research_pack(
            create_research_pack(retrieval_request),
            parent_pack_id=request.parent_pack_id,
            pack_version=pack_version,
        )
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            repo.save_research_pack(
                pack=pack,
                case_id=effective_case_id,
                source_thread_id=request.source_thread_id,
                source_agent_run_id=request.source_agent_run_id,
                created_by_user_id=auth.user_id,
                purpose=request.purpose,
            )
            repo.record_audit_event(
                organization_id=organization_id,
                case_id=effective_case_id,
                user_id=auth.user_id,
                event_type="research_pack.created",
                entity_type="research_pack",
                entity_id=pack.pack_id,
                after_state={
                    "pack_id": pack.pack_id,
                    "pack_hash": research_pack_hash(pack),
                    "pack_version": pack.pack_version,
                    "parent_pack_id": pack.parent_pack_id,
                    "item_count": len(pack.items),
                    "missing_source_summary_present": bool(pack.missing_source_summary),
                },
                metadata={
                    "query_sha256": _sha256_text(request.query),
                    "query_char_count": len(request.query),
                    "query_class": request.query_class.value,
                    "max_pack_items": request.max_pack_items,
                    "max_pack_tokens": request.max_pack_tokens,
                    "purpose": request.purpose,
                    "parent_pack_id": request.parent_pack_id,
                    "source_thread_id": request.source_thread_id,
                    "source_agent_run_id": request.source_agent_run_id,
                },
            )
    except HTTPException:
        raise
    except RetrievalServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return pack.model_dump(mode="json")


@app.get("/v1/research/packs/{pack_id}/items/{pack_item_id}/source")
def get_research_pack_item_source(
    pack_id: str,
    pack_item_id: str,
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        authorized_case_id = _require_research_pack_access_permission(repo, pack_id=pack_id, user_id=auth.user_id)
        organization_id = _audit_organization_id(repo, user_id=auth.user_id, case_id=authorized_case_id)
        source = repo.get_pack_item_source(pack_id=pack_id, pack_item_id=pack_item_id)
        if source is not None:
            repo.record_audit_event(
                organization_id=organization_id,
                case_id=authorized_case_id,
                user_id=auth.user_id,
                event_type="research_pack.source.viewed",
                entity_type="research_pack_item",
                entity_id=pack_item_id,
                after_state={
                    "pack_id": pack_id,
                    "pack_item_id": pack_item_id,
                    "chunk_id": source.chunk_id,
                    "document_id": source.document_id,
                    "page_start": source.page_start,
                    "page_end": source.page_end,
                    "context_source": source.context_source,
                    "anchor_status": source.anchor_status,
                },
                metadata={
                    "citation": source.citation,
                    "document_type": source.document_type,
                    "source_id": source.source_id,
                    "authority_level": source.authority_level,
                    "page_text_available": source.page_text_available,
                },
            )
    if source is None:
        raise HTTPException(status_code=404, detail=f"Pack item not found: {pack_item_id}")
    return source.model_dump(mode="json")


@app.get("/v1/ui/cases/{case_id}/workspace", response_model=CaseWorkspaceSnapshot)
def get_case_workspace_snapshot(
    case_id: str,
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        snapshot = repo.case_workspace_snapshot(case_id=case_id, user_id=auth.user_id)
        repo.record_audit_event(
            organization_id=case_context.organization_id,
            case_id=case_id,
            user_id=auth.user_id,
            event_type="case.workspace.viewed",
            entity_type="case",
            entity_id=case_id,
            after_state={
                "project_count": len(snapshot["projects"]),
                "case_count": len(snapshot["cases"]),
                "message_count": len(snapshot["messages"]),
                "document_count": len(snapshot["documents"]),
                "pack_item_count": len(snapshot["researchPackItems"]),
                "draft_count": len(snapshot["drafts"]),
                "review_item_count": len(snapshot["reviewItems"]),
            },
        )
    return CaseWorkspaceSnapshot.model_validate(snapshot).model_dump(mode="json")


@app.get("/v1/ui/cases/{case_id}/documents", response_model=WorkspaceDocumentPageResponse)
def list_workspace_documents(
    case_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        page = repo.case_workspace_documents_page(case_id=case_id, limit=limit, offset=offset)
        repo.record_audit_event(
            organization_id=case_context.organization_id,
            case_id=case_id,
            user_id=auth.user_id,
            event_type="case.documents.page_viewed",
            entity_type="case",
            entity_id=case_id,
            after_state={
                "document_count": len(page["documents"]),
                "limit": limit,
                "offset": offset,
                "has_more": page["hasMore"],
            },
        )
    return WorkspaceDocumentPageResponse.model_validate(page).model_dump(mode="json")


@app.get("/v1/ui/cases/{case_id}/documents/{document_id}/file")
def get_workspace_document_file(
    case_id: str,
    document_id: str,
    auth: AuthContext = Depends(require_auth_context),
) -> FileResponse:
    context: dict[str, object] | None = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        context = repo.case_document_file_context(case_id=case_id, document_id=document_id)
        if context is not None and context.get("case_file_available"):
            repo.record_audit_event(
                organization_id=case_context.organization_id,
                case_id=case_id,
                user_id=auth.user_id,
                event_type="case.document.file.viewed",
                entity_type="document",
                entity_id=document_id,
                after_state={
                    "document_id": document_id,
                    "case_file_name": context.get("case_file_name"),
                    "viewer_mime_type": context.get("viewer_mime_type"),
                },
                metadata={"source": "case_workspace_ui"},
            )
    if context is None:
        raise HTTPException(status_code=404, detail=f"Case document not found: {document_id}")
    file_path = context.get("effective_file_path")
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Case file is not cached for document: {document_id}")
    filename = str(context.get("case_file_name") or document_id)
    headers = {
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
    }
    return FileResponse(
        path=str(file_path),
        media_type=str(context.get("viewer_mime_type") or "application/octet-stream"),
        headers=headers,
    )


@app.post("/v1/ui/cases/{case_id}/documents/{document_id}/cache", response_model=WorkspaceDocumentFileResponse)
def cache_workspace_document_file(
    case_id: str,
    document_id: str,
    _body_size: None = Depends(UI_DOCUMENT_CACHE_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    blocked_rate_limit: RateLimitResult | None = None
    context: dict[str, object] | None = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        rate_limit_result = _consume_rate_limit(
            repo,
            organization_id=case_context.organization_id,
            user_id=auth.user_id,
            policy=UI_DOCUMENT_CACHE_RATE_LIMIT,
        )
        if not rate_limit_result.allowed:
            _record_rate_limit_rejection(
                repo,
                organization_id=case_context.organization_id,
                case_id=case_id,
                user_id=auth.user_id,
                result=rate_limit_result,
            )
            blocked_rate_limit = rate_limit_result
        else:
            try:
                context = repo.cache_case_document_file(case_id=case_id, document_id=document_id)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            if context is not None:
                repo.record_audit_event(
                    organization_id=case_context.organization_id,
                    case_id=case_id,
                    user_id=auth.user_id,
                    event_type="case.document.file.cached",
                    entity_type="document",
                    entity_id=document_id,
                    after_state={
                        "document_id": document_id,
                        "case_file_available": context.get("case_file_available"),
                        "case_file_name": context.get("case_file_name"),
                    },
                    metadata={"source": "case_workspace_ui"},
                )
    if blocked_rate_limit is not None:
        _raise_rate_limit_exceeded(blocked_rate_limit)
    if context is None:
        raise HTTPException(status_code=404, detail=f"Case document not found: {document_id}")
    return WorkspaceDocumentFileResponse.model_validate(
        _workspace_document_file_response(case_id=case_id, context=context)
    ).model_dump(mode="json")


@app.get("/v1/ui/cases/{case_id}/documents/{document_id}/status", response_model=WorkspaceDocument)
def get_workspace_document_status(
    case_id: str,
    document_id: str,
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    document: dict[str, object] | None = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        document = repo.case_workspace_document(case_id=case_id, document_id=document_id)
        if document is not None:
            repo.record_audit_event(
                organization_id=case_context.organization_id,
                case_id=case_id,
                user_id=auth.user_id,
                event_type="case.document.status.viewed",
                entity_type="document",
                entity_id=document_id,
                after_state={
                    "document_id": document_id,
                    "case_file_available": document.get("caseFileAvailable"),
                    "page_count": document.get("pageCount"),
                    "quality_flags": document.get("qualityFlags"),
                    "text_preview_available": bool(str(document.get("textPreview") or "").strip()),
                },
                metadata={"source": "case_workspace_ui"},
            )
    if document is None:
        raise HTTPException(status_code=404, detail=f"Case document not found: {document_id}")
    return WorkspaceDocument.model_validate(document).model_dump(mode="json")


@app.post("/v1/ui/cases", response_model=WorkspaceCaseCreateResponse)
def create_workspace_case(
    request: WorkspaceCaseCreateRequest,
    _body_size: None = Depends(UI_CASE_CREATE_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    blocked_rate_limit: RateLimitResult | None = None
    created = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        user_context = _require_active_user(repo, auth.user_id)
        rate_limit_result = _consume_rate_limit(
            repo,
            organization_id=user_context.organization_id,
            user_id=auth.user_id,
            policy=UI_CASE_CREATE_RATE_LIMIT,
        )
        if not rate_limit_result.allowed:
            _record_rate_limit_rejection(
                repo,
                organization_id=user_context.organization_id,
                case_id=None,
                user_id=auth.user_id,
                result=rate_limit_result,
            )
            blocked_rate_limit = rate_limit_result
        else:
            try:
                created = repo.create_case_for_user(
                    user_id=auth.user_id,
                    title=request.title,
                    project_id=request.projectId,
                    project_name=request.projectName,
                    case_number=request.caseNumber,
                    court=request.court,
                    matter_type=request.matterType,
                )
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            repo.record_audit_event(
                organization_id=user_context.organization_id,
                case_id=created.case_id,
                user_id=auth.user_id,
                event_type="case.created",
                entity_type="case",
                entity_id=created.case_id,
                after_state={
                    "case_id": created.case_id,
                    "project_id": created.project_id,
                    "title": request.title,
                    "court": request.court,
                    "matter_type": request.matterType,
                },
                metadata={"source": "case_workspace_ui"},
            )
    if blocked_rate_limit is not None:
        _raise_rate_limit_exceeded(blocked_rate_limit)
    if created is None:
        raise HTTPException(status_code=500, detail="Case creation did not complete")
    return WorkspaceCaseCreateResponse(caseId=created.case_id, projectId=created.project_id).model_dump(mode="json")


@app.post("/v1/ui/cases/{case_id}/messages", response_model=WorkspaceChatMessageCreateResponse)
def create_workspace_chat_message(
    case_id: str,
    request: WorkspaceChatMessageCreateRequest,
    _body_size: None = Depends(UI_CHAT_MESSAGE_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    blocked_rate_limit: RateLimitResult | None = None
    user_message: dict[str, object] | None = None
    assistant_message: dict[str, object] | None = None
    agent_run_id: str | None = None
    organization_id: str | None = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        organization_id = case_context.organization_id
        rate_limit_result = _consume_rate_limit(
            repo,
            organization_id=case_context.organization_id,
            user_id=auth.user_id,
            policy=UI_CHAT_MESSAGE_RATE_LIMIT,
        )
        if not rate_limit_result.allowed:
            _record_rate_limit_rejection(
                repo,
                organization_id=case_context.organization_id,
                case_id=case_id,
                user_id=auth.user_id,
                result=rate_limit_result,
            )
            blocked_rate_limit = rate_limit_result
        else:
            try:
                user_message = repo.add_case_user_message(
                    organization_id=case_context.organization_id,
                    case_id=case_id,
                    user_id=auth.user_id,
                    content=request.content,
                    thread_id=request.threadId,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            agent_run_id = repo.create_agent_run(
                organization_id=case_context.organization_id,
                case_id=case_id,
                thread_id=str(user_message["threadId"]),
                agent_type="pack_bounded_chat",
                model="hybrid_retrieval",
                status="running",
                input_payload={
                    "query": request.content,
                    "thread_id": user_message["threadId"],
                    "parent_message_id": user_message["messageId"],
                    "max_pack_items": UI_CHAT_RESEARCH_MAX_PACK_ITEMS,
                    "max_pack_tokens": UI_CHAT_RESEARCH_MAX_PACK_TOKENS,
                },
            )
            repo.record_audit_event(
                organization_id=case_context.organization_id,
                case_id=case_id,
                user_id=auth.user_id,
                event_type="chat.message.created",
                entity_type="chat_message",
                entity_id=user_message["messageId"],
                after_state={
                    "message_id": user_message["messageId"],
                    "thread_id": user_message["threadId"],
                    "role": user_message["role"],
                    "agent_run_id": agent_run_id,
                },
                metadata={
                    "content_sha256": _sha256_text(request.content),
                    "content_char_count": len(request.content),
                    "source": "case_workspace_ui",
                },
            )
    if blocked_rate_limit is not None:
        _raise_rate_limit_exceeded(blocked_rate_limit)
    if user_message is None or organization_id is None:
        raise HTTPException(status_code=500, detail="Chat message creation did not complete")

    retrieval_status: Literal["complete", "empty", "failed"] = "complete"
    pack_id: str | None = None
    try:
        pack = create_research_pack(
            ResearchQueryRequest(
                query=request.content,
                query_class="general_research",
                case_id=case_id,
                source_thread_id=str(user_message["threadId"]),
                source_agent_run_id=agent_run_id,
                created_by_user_id=auth.user_id,
                purpose="pack_bounded_chat",
                max_pack_items=UI_CHAT_RESEARCH_MAX_PACK_ITEMS,
                max_pack_tokens=UI_CHAT_RESEARCH_MAX_PACK_TOKENS,
            )
        )
        pack_id = pack.pack_id
        if not pack.items:
            retrieval_status = "empty"
        assistant_content = _pack_bounded_chat_response(query=request.content, pack=pack)
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            repo.save_research_pack(
                pack=pack,
                case_id=case_id,
                source_thread_id=str(user_message["threadId"]),
                source_agent_run_id=agent_run_id,
                created_by_user_id=auth.user_id,
                purpose="pack_bounded_chat",
            )
            assistant_message = repo.add_case_assistant_message(
                case_id=case_id,
                thread_id=str(user_message["threadId"]),
                content=assistant_content,
                parent_message_id=str(user_message["messageId"]),
                pack_id=pack.pack_id,
                agent_run_id=agent_run_id,
                metadata={
                    "pack_hash": research_pack_hash(pack),
                    "retrieval_status": retrieval_status,
                    "pack_item_count": len(pack.items),
                },
            )
            if agent_run_id:
                repo.update_agent_run_status(
                    agent_run_id=agent_run_id,
                    status="complete",
                    output_payload={
                        "pack_id": pack.pack_id,
                        "pack_hash": research_pack_hash(pack),
                        "pack_item_count": len(pack.items),
                        "retrieval_status": retrieval_status,
                    },
                )
            repo.record_audit_event(
                organization_id=organization_id,
                case_id=case_id,
                user_id=auth.user_id,
                event_type="chat.assistant.created",
                entity_type="chat_message",
                entity_id=assistant_message["messageId"],
                after_state={
                    "message_id": assistant_message["messageId"],
                    "thread_id": assistant_message["threadId"],
                    "role": assistant_message["role"],
                    "pack_id": pack.pack_id,
                    "pack_item_count": len(pack.items),
                },
                metadata={
                    "source": "case_workspace_ui",
                    "pack_hash": research_pack_hash(pack),
                    "retrieval_status": retrieval_status,
                },
            )
    except Exception as exc:
        retrieval_status = "failed"
        assistant_content = (
            "I saved your message, but I could not build a cited research pack for it yet. "
            "No legal conclusion has been generated because pack-bounded retrieval failed."
        )
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            assistant_message = repo.add_case_assistant_message(
                case_id=case_id,
                thread_id=str(user_message["threadId"]),
                content=assistant_content,
                parent_message_id=str(user_message["messageId"]),
                agent_run_id=agent_run_id,
                metadata={"retrieval_status": retrieval_status, "error": str(exc)[:1000]},
            )
            if agent_run_id:
                repo.update_agent_run_status(agent_run_id=agent_run_id, status="failed", error=str(exc)[:2000])

    messages = [WorkspaceChatMessage.model_validate(user_message)]
    if assistant_message is not None:
        messages.append(WorkspaceChatMessage.model_validate(assistant_message))
    return WorkspaceChatMessageCreateResponse(
        messages=messages,
        packId=pack_id,
        retrievalStatus=retrieval_status,
    ).model_dump(mode="json")


@app.get("/v1/cases/{case_id}/review/items", response_model=ReviewQueueResponse)
def list_case_review_items(
    case_id: str,
    auth: AuthContext = Depends(require_auth_context),
    status: str | None = "pending",
    item_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    status_filter = _normalize_all_filter(status)
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        items = repo.list_review_items(
            case_id=case_id,
            status=status_filter,
            item_type=item_type,
            limit=limit,
        )
    return ReviewQueueResponse(
        case_id=case_id,
        status=status_filter,
        item_type=item_type,
        items=items,
    ).model_dump(mode="json")


@app.post("/v1/cases/{case_id}/review/items/{review_item_id}/decision", response_model=ReviewDecisionResponse)
def record_review_decision(
    case_id: str,
    review_item_id: str,
    request: ReviewDecisionRequest,
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    try:
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            _require_case_permission(
                repo,
                case_id=case_id,
                user_id=auth.user_id,
            )
            result = repo.apply_review_decision(
                case_id=case_id,
                review_item_id=review_item_id,
                reviewer_user_id=auth.user_id,
                decision=request.decision,
                comment=request.comment,
            )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"Review item not found for case: {review_item_id}")
    return ReviewDecisionResponse(
        case_id=case_id,
        review_item=result.review_item,
        target_item_type=result.target_item_type,
        target_item_id=result.target_item_id,
        target_status=result.target_status,
        audit_event_id=result.audit_event_id,
    ).model_dump(mode="json")


@app.get("/v1/cases/{case_id}/drafts", response_model=DraftListResponse)
def list_case_drafts(
    case_id: str,
    auth: AuthContext = Depends(require_auth_context),
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    status_filter = _normalize_all_filter(status)
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        drafts = repo.list_case_drafts(case_id=case_id, status=status_filter, limit=limit)
    return DraftListResponse(case_id=case_id, status=status_filter, drafts=drafts).model_dump(mode="json")


@app.get("/v1/cases/{case_id}/drafts/{draft_id}", response_model=DraftDetail)
def get_case_draft(
    case_id: str,
    draft_id: str,
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        draft = repo.get_draft_detail(case_id=case_id, draft_id=draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"Draft not found for case: {draft_id}")
    return DraftDetail.model_validate(draft).model_dump(mode="json")


@app.get("/v1/cases/{case_id}/claims", response_model=ClaimListResponse)
def list_case_claims(
    case_id: str,
    auth: AuthContext = Depends(require_auth_context),
    pack_id: str | None = None,
    support_status: str | None = None,
    draft_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    support_status_filter = _normalize_all_filter(support_status)
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        claims = repo.list_case_claims(
            case_id=case_id,
            pack_id=pack_id,
            support_status=support_status_filter,
            draft_id=draft_id,
            limit=limit,
        )
    return ClaimListResponse(
        case_id=case_id,
        pack_id=pack_id,
        support_status=support_status_filter,
        draft_id=draft_id,
        claims=claims,
    ).model_dump(mode="json")


@app.get("/v1/cases/{case_id}/claims/{claim_id}", response_model=ClaimDetail)
def get_case_claim(
    case_id: str,
    claim_id: str,
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        claim = repo.get_claim_detail(case_id=case_id, claim_id=claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim not found for case: {claim_id}")
    return ClaimDetail.model_validate(claim).model_dump(mode="json")


@app.post(
    "/v1/cases/{case_id}/evidence/assessments",
    response_model=EvidenceAssessmentCreateResponse,
)
def create_case_evidence_assessment(
    case_id: str,
    request: ClaimEvidenceAssessmentRequest,
    _body_size: None = Depends(EVIDENCE_ASSESSMENT_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        case_context = _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        try:
            assessment = repo.add_claim_evidence_assessment(
                case_id=case_id,
                assessment=request,
                created_by_user_id=auth.user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        repo.record_audit_event(
            organization_id=case_context.organization_id,
            case_id=case_id,
            user_id=auth.user_id,
            event_type="evidence.assessment.recorded",
            entity_type="claim_evidence_assessment",
            entity_id=str(assessment["assessment_id"]),
            after_state=assessment,
            metadata={
                "claim_id": assessment["claim_id"],
                "pack_id": assessment["pack_id"],
                "pack_item_id": assessment["pack_item_id"],
                "stance": assessment["stance"],
                "citation_role": assessment["citation_role"],
            },
        )
    return EvidenceAssessmentCreateResponse(case_id=case_id, assessment=assessment).model_dump(mode="json")


@app.get(
    "/v1/cases/{case_id}/evidence/assessments",
    response_model=EvidenceAssessmentGroupedResponse,
)
def list_case_evidence_assessments(
    case_id: str,
    auth: AuthContext = Depends(require_auth_context),
    claim_id: str | None = None,
    pack_id: str | None = None,
    stance: EvidenceStance | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        grouped = repo.grouped_claim_evidence_assessments(
            case_id=case_id,
            claim_id=claim_id,
            pack_id=pack_id,
            stance=stance,
            limit=limit,
        )
    return EvidenceAssessmentGroupedResponse.model_validate(grouped).model_dump(mode="json")


@app.get("/v1/cases/{case_id}/audit/events", response_model=AuditEventListResponse)
def list_case_audit_events(
    case_id: str,
    auth: AuthContext = Depends(require_auth_context),
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
) -> dict[str, object]:
    event_type_filter = _normalize_all_filter(event_type)
    entity_type_filter = _normalize_all_filter(entity_type)
    entity_id_filter = _normalize_all_filter(entity_id)
    before_created_at, before_audit_event_id = _decode_audit_cursor(cursor)
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        _require_case_permission(repo, case_id=case_id, user_id=auth.user_id)
        events = repo.list_case_audit_events(
            case_id=case_id,
            event_type=event_type_filter,
            entity_type=entity_type_filter,
            entity_id=entity_id_filter,
            before_created_at=before_created_at,
            before_audit_event_id=before_audit_event_id,
            limit=limit + 1,
        )
    page_events, next_cursor = _audit_page(events, limit)
    return AuditEventListResponse(
        case_id=case_id,
        event_type=event_type_filter,
        entity_type=entity_type_filter,
        entity_id=entity_id_filter,
        next_cursor=next_cursor,
        events=page_events,
    ).model_dump(mode="json")


@app.get("/v1/audit/events", response_model=AuditEventStreamResponse)
def list_audit_events(
    auth: AuthContext = Depends(require_auth_context),
    scope: str = "user",
    user_id: str | None = None,
    case_id: str | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = None,
) -> dict[str, object]:
    scope_filter = _normalize_all_filter(scope) or "user"
    if scope_filter not in {"user", "organization"}:
        raise HTTPException(status_code=422, detail="scope must be 'user' or 'organization'")
    requested_user_id = _normalize_all_filter(user_id)
    case_id_filter = _normalize_all_filter(case_id)
    event_type_filter = _normalize_all_filter(event_type)
    entity_type_filter = _normalize_all_filter(entity_type)
    entity_id_filter = _normalize_all_filter(entity_id)
    before_created_at, before_audit_event_id = _decode_audit_cursor(cursor)

    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        user_context = _require_active_user(repo, auth.user_id)
        if user_context.organization_id is None:
            raise HTTPException(status_code=403, detail="Authenticated user is not attached to an organization")
        organization_id = user_context.organization_id
        has_org_audit_access = repo.user_has_organization_audit_access(
            organization_id=organization_id,
            user_id=auth.user_id,
        )
        if scope_filter == "organization":
            if not has_org_audit_access:
                raise HTTPException(status_code=403, detail="Organization audit access is required")
            effective_user_id = requested_user_id
        else:
            if requested_user_id and requested_user_id != auth.user_id:
                raise HTTPException(status_code=403, detail="Use organization scope to view another user's audit events")
            effective_user_id = auth.user_id
            if case_id_filter is not None:
                _require_case_permission(repo, case_id=case_id_filter, user_id=auth.user_id)

        events = repo.list_audit_events(
            organization_id=organization_id,
            user_id=effective_user_id,
            case_id=case_id_filter,
            event_type=event_type_filter,
            entity_type=entity_type_filter,
            entity_id=entity_id_filter,
            before_created_at=before_created_at,
            before_audit_event_id=before_audit_event_id,
            limit=limit + 1,
        )
    page_events, next_cursor = _audit_page(events, limit)
    return AuditEventStreamResponse(
        scope=scope_filter,
        organization_id=organization_id,
        user_id=effective_user_id,
        case_id=case_id_filter,
        event_type=event_type_filter,
        entity_type=entity_type_filter,
        entity_id=entity_id_filter,
        next_cursor=next_cursor,
        events=page_events,
    ).model_dump(mode="json")


@app.post("/v1/strategy/prompt")
def create_strategy_prompt(
    request: StrategyDraftRequest,
    _body_size: None = Depends(STRATEGY_PROMPT_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    messages: list[dict[str, str]] | None = None
    rate_limit_result = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        if request.case_id is not None:
            case_context = _require_case_permission(
                repo,
                case_id=request.case_id,
                user_id=auth.user_id,
            )
            organization_id = case_context.organization_id
        else:
            organization_id = _require_active_user(repo, auth.user_id).organization_id
        rate_limit_result = _consume_rate_limit(
            repo,
            organization_id=organization_id,
            user_id=auth.user_id,
            policy=STRATEGY_PROMPT_RATE_LIMIT,
        )
        if not rate_limit_result.allowed:
            _record_rate_limit_rejection(
                repo,
                organization_id=organization_id,
                case_id=request.case_id,
                user_id=auth.user_id,
                result=rate_limit_result,
            )
        else:
            pack = _load_authorized_research_pack(
                repo,
                pack_id=request.pack_id,
                user_id=auth.user_id,
                case_id=request.case_id,
            )
            messages = build_strategy_prompt(request.case_facts, pack)
            repo.record_audit_event(
                organization_id=organization_id,
                case_id=request.case_id,
                user_id=auth.user_id,
                event_type="strategy.prompt.built",
                entity_type="research_pack",
                entity_id=pack.pack_id,
                after_state={
                    "pack_id": pack.pack_id,
                    "message_count": len(messages),
                    "pack_item_count": len(pack.items),
                },
                metadata={
                    "case_facts_sha256": _sha256_text(request.case_facts),
                    "case_facts_char_count": len(request.case_facts),
                    "pack_hash": research_pack_hash(pack),
                    "requested_output": request.requested_output,
                },
            )
    if rate_limit_result is not None and not rate_limit_result.allowed:
        _raise_rate_limit_exceeded(rate_limit_result)
    if messages is None:
        raise HTTPException(status_code=500, detail="Strategy prompt was not built")
    return {"pack_id": request.pack_id, "messages": messages}


@app.post("/v1/cases/structure")
def structure_case_facts(
    request: CaseStructureRequest,
    _body_size: None = Depends(CASE_STRUCTURE_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    rate_limit_result = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        user_context = _require_active_user(repo, auth.user_id)
        rate_limit_result = _consume_rate_limit(
            repo,
            organization_id=user_context.organization_id,
            user_id=auth.user_id,
            policy=CASE_STRUCTURE_RATE_LIMIT,
        )
        if not rate_limit_result.allowed:
            _record_rate_limit_rejection(
                repo,
                organization_id=user_context.organization_id,
                case_id=None,
                user_id=auth.user_id,
                result=rate_limit_result,
            )
    if rate_limit_result is not None and not rate_limit_result.allowed:
        _raise_rate_limit_exceeded(rate_limit_result)
    try:
        client = AzureChatClient(load_azure_chat_config(".env.azure-openai"))
        structure = generate_case_structure(
            raw_input=request.raw_input,
            client=client,
            max_completion_tokens=request.max_completion_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with session_scope() as session:
        LegalWorkspaceRepository(session).record_audit_event(
            organization_id=user_context.organization_id,
            case_id=None,
            user_id=auth.user_id,
            event_type="case.structure.generated",
            entity_type="case_structure",
            entity_id=structure.raw_input_sha256,
            after_state={
                "raw_input_sha256": structure.raw_input_sha256,
                "fact_count": len(structure.facts),
                "issue_count": len(structure.issues),
                "timeline_count": len(structure.timeline),
                "retrieval_query_count": len(structure.retrieval_queries),
                "warning_count": len(structure.warnings),
            },
            metadata={
                "raw_input_sha256": _sha256_text(request.raw_input),
                "raw_input_char_count": len(request.raw_input),
                "max_completion_tokens": request.max_completion_tokens,
            },
        )
    return structure.model_dump(mode="json")


@app.post("/v1/strategy/draft", response_model=PersistedStrategyDraftResponse)
def create_strategy_draft_endpoint(
    request: StrategyDraftRequest,
    _body_size: None = Depends(STRATEGY_DRAFT_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    if request.case_id is None:
        raise HTTPException(status_code=422, detail="case_id is required so strategy drafts can be audited and reviewed")

    try:
        config = load_azure_chat_config(".env.azure-openai")
        client = AzureChatClient(config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    agent_run_id = request.agent_run_id
    created_by_user_id: str | None = None
    assigned_review_user_id: str | None = None
    rate_limit_result = None
    research_pack: LegalResearchPack | None = None
    try:
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            case_context = _require_case_permission(
                repo,
                case_id=request.case_id,
                user_id=auth.user_id,
            )
            created_by_user_id = auth.user_id
            assigned_review_user_id = request.assigned_review_user_id or created_by_user_id
            if assigned_review_user_id and not repo.user_has_case_permission(
                case_id=request.case_id,
                user_id=assigned_review_user_id,
            ):
                raise HTTPException(
                    status_code=403,
                    detail=f"Assigned reviewer does not have permission on case: {assigned_review_user_id}",
                )
            if request.thread_id and not repo.thread_belongs_to_case(case_id=request.case_id, thread_id=request.thread_id):
                raise HTTPException(status_code=422, detail=f"Thread does not belong to case: {request.thread_id}")
            if request.message_id:
                if not request.thread_id:
                    raise HTTPException(status_code=422, detail="thread_id is required when message_id is supplied")
                if not repo.message_belongs_to_thread(thread_id=request.thread_id, message_id=request.message_id):
                    raise HTTPException(status_code=422, detail=f"Message does not belong to thread: {request.message_id}")
            if agent_run_id:
                if not repo.agent_run_belongs_to_case(case_id=request.case_id, agent_run_id=agent_run_id):
                    raise HTTPException(status_code=422, detail=f"Agent run does not belong to case: {agent_run_id}")
            rate_limit_result = _consume_rate_limit(
                repo,
                organization_id=case_context.organization_id,
                user_id=auth.user_id,
                policy=STRATEGY_DRAFT_RATE_LIMIT,
            )
            if not rate_limit_result.allowed:
                _record_rate_limit_rejection(
                    repo,
                    organization_id=case_context.organization_id,
                    case_id=request.case_id,
                    user_id=auth.user_id,
                    result=rate_limit_result,
                )
            else:
                research_pack = _load_authorized_research_pack(
                    repo,
                    pack_id=request.pack_id,
                    user_id=auth.user_id,
                    case_id=request.case_id,
                    require_case_link=True,
                )
                if not research_pack.items:
                    raise HTTPException(status_code=422, detail="Research pack must contain at least one cited source")
                if not agent_run_id:
                    agent_run_id = repo.create_agent_run(
                        organization_id=case_context.organization_id,
                        case_id=request.case_id,
                        thread_id=request.thread_id,
                        agent_type="strategy_drafting",
                        model=config.deployment_name,
                        status="running",
                        input_payload=_strategy_agent_input_payload(request, research_pack=research_pack),
                    )
        if rate_limit_result is not None and not rate_limit_result.allowed:
            _raise_rate_limit_exceeded(rate_limit_result)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        if research_pack is None:
            raise HTTPException(status_code=500, detail="Research pack was not loaded")
        draft = generate_strategy_draft(
            case_facts=request.case_facts,
            pack=research_pack,
            requested_output=request.requested_output,
            client=client,
        )
    except ValueError as exc:
        _mark_agent_failed(agent_run_id, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _mark_agent_failed(agent_run_id, str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            persisted = repo.persist_strategy_draft(
                case_id=request.case_id,
                thread_id=request.thread_id,
                parent_message_id=request.message_id,
                agent_run_id=agent_run_id,
                created_by_user_id=created_by_user_id,
                assigned_review_user_id=assigned_review_user_id,
                requested_output=request.requested_output,
                research_pack=research_pack,
                strategy_response=draft,
            )
            repo.update_agent_run_status(
                agent_run_id=agent_run_id,
                status="complete",
                output_payload={
                    "draft_id": persisted.draft_id,
                    "message_id": persisted.message_id,
                    "claim_ids": persisted.claim_ids,
                    "draft_review_item_id": persisted.draft_review_item_id,
                    "claim_review_item_ids": persisted.claim_review_item_ids,
                    "reasoning_review_item_ids": persisted.reasoning_review_item_ids,
                    "counterargument_count": len(draft.counterarguments),
                    "risk_count": len(draft.risk_rankings),
                    "next_retrieval_question_count": len(draft.next_retrieval_questions),
                    "citation_validation": draft.citation_validation,
                    "missing_authorities": draft.missing_authorities,
                    "warnings": draft.warnings,
                    "reasoning_pack_present": draft.reasoning_pack is not None,
                },
            )
    except ValueError as exc:
        _mark_agent_failed(agent_run_id, str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _mark_agent_failed(agent_run_id, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return PersistedStrategyDraftResponse(
        **draft.model_dump(mode="json"),
        case_id=request.case_id,
        thread_id=request.thread_id,
        draft_id=persisted.draft_id,
        message_id=persisted.message_id,
        agent_run_id=agent_run_id,
        claim_ids=persisted.claim_ids,
        draft_review_item_id=persisted.draft_review_item_id,
        claim_review_item_ids=persisted.claim_review_item_ids,
        reasoning_review_item_ids=persisted.reasoning_review_item_ids,
    ).model_dump(mode="json")


@app.post("/v1/strategy/validate")
def validate_strategy_output(
    request: StrategyDraftResponse,
    _body_size: None = Depends(STRATEGY_VALIDATE_BODY_LIMIT),
    auth: AuthContext = Depends(require_auth_context),
) -> dict[str, object]:
    unknown: list[str] | None = None
    rate_limit_result = None
    with session_scope() as session:
        repo = LegalWorkspaceRepository(session)
        authorized_case_id = _require_research_pack_access_permission(repo, pack_id=request.pack_id, user_id=auth.user_id)
        organization_id = _audit_organization_id(repo, user_id=auth.user_id, case_id=authorized_case_id)
        rate_limit_result = _consume_rate_limit(
            repo,
            organization_id=organization_id,
            user_id=auth.user_id,
            policy=STRATEGY_VALIDATE_RATE_LIMIT,
        )
        if not rate_limit_result.allowed:
            _record_rate_limit_rejection(
                repo,
                organization_id=organization_id,
                case_id=authorized_case_id,
                user_id=auth.user_id,
                result=rate_limit_result,
            )
        else:
            pack_items = repo.research_pack_item_ids(request.pack_id)
            if not pack_items:
                raise HTTPException(status_code=404, detail=f"Research pack not found or has no items: {request.pack_id}")
            cited = set(request.all_pack_item_ids()).union(extract_pack_item_references(request.answer))
            unknown = sorted(cited.difference(pack_items))
            repo.record_audit_event(
                organization_id=organization_id,
                case_id=authorized_case_id,
                user_id=auth.user_id,
                event_type="strategy.validation.checked",
                entity_type="research_pack",
                entity_id=request.pack_id,
                after_state={
                    "pack_id": request.pack_id,
                    "valid": not unknown,
                    "cited_pack_item_count": len(cited),
                    "stored_pack_item_count": len(pack_items),
                    "unknown_pack_item_count": len(unknown),
                },
                metadata={
                    "claim_count": len(request.claims),
                    "answer_sha256": _sha256_text(request.answer),
                    "answer_char_count": len(request.answer),
                    "unknown_pack_item_ids": unknown,
                },
            )
    if rate_limit_result is not None and not rate_limit_result.allowed:
        _raise_rate_limit_exceeded(rate_limit_result)
    if unknown is None:
        raise HTTPException(status_code=500, detail="Strategy validation did not complete")
    return {"valid": not unknown, "unknown_pack_item_ids": unknown}


def _strategy_agent_input_payload(
    request: StrategyDraftRequest,
    *,
    research_pack: LegalResearchPack,
) -> dict[str, object]:
    return {
        "case_id": request.case_id,
        "thread_id": request.thread_id,
        "parent_message_id": request.message_id,
        "requested_output": request.requested_output,
        "pack_id": research_pack.pack_id,
        "pack_hash": research_pack_hash(research_pack),
        "pack_item_count": len(research_pack.items),
        "case_facts_sha256": hashlib.sha256(request.case_facts.encode("utf-8")).hexdigest(),
        "case_facts_char_count": len(request.case_facts),
    }


def _pack_bounded_chat_response(*, query: str, pack: LegalResearchPack) -> str:
    if not pack.items:
        return (
            "I could not find a cited authority in the current indexed corpus for this message. "
            "No legal conclusion is generated from an empty research pack. Try adding more facts, a statute name, "
            "a citation, a date range, or a court/source filter."
        )

    lines = [
        "I found a cited research pack for your question. I am using only the retrieved pack items below.",
        "",
        f"Question: {query}",
        f"Pack: {pack.pack_id}",
        "",
        "Most relevant cited authorities:",
    ]
    for index, item in enumerate(pack.items[:5], start=1):
        page = ""
        if item.page_start is not None:
            page = f", p. {item.page_start}" if item.page_end in (None, item.page_start) else f", pp. {item.page_start}-{item.page_end}"
        excerpt = " ".join(item.text.split())
        if len(excerpt) > 420:
            excerpt = f"{excerpt[:417].rstrip()}..."
        lines.extend(
            [
                f"{index}. {item.citation}{page} [{item.pack_item_id}]",
                f"   {excerpt}",
            ]
        )

    lines.extend(
        [
            "",
            "Use this as a source review starting point only. Strategy or drafting should cite these exact pack_item_id values and request more retrieval if a necessary authority is missing.",
        ]
    )
    if pack.source_warnings:
        lines.extend(["", "Pack warnings:", *[f"- {warning}" for warning in pack.source_warnings[:5]]])
    if pack.missing_source_summary:
        lines.extend(["", f"Missing source note: {pack.missing_source_summary}"])
    return "\n".join(lines)


def _mark_agent_failed(agent_run_id: str | None, error: str) -> None:
    if not agent_run_id:
        return
    try:
        with session_scope() as session:
            LegalWorkspaceRepository(session).update_agent_run_status(
                agent_run_id=agent_run_id,
                status="failed",
                error=error,
            )
    except Exception:
        return


def _require_case(repo: LegalWorkspaceRepository, case_id: str) -> None:
    if repo.case_context(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")


def _require_case_permission(
    repo: LegalWorkspaceRepository,
    *,
    case_id: str,
    user_id: str | None,
):
    case_context = repo.case_context(case_id)
    if case_context is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user ID is required for case-scoped access")
    if not repo.user_has_case_permission(case_id=case_id, user_id=user_id):
        raise HTTPException(status_code=403, detail=f"User does not have permission on case: {user_id}")
    return case_context


def _require_active_user(repo: LegalWorkspaceRepository, user_id: str):
    user_context = repo.user_context(user_id)
    if user_context is None:
        raise HTTPException(status_code=403, detail=f"Authenticated user is not active: {user_id}")
    return user_context


def _workspace_document_file_response(*, case_id: str, context: dict[str, object]) -> dict[str, object]:
    document_id = str(context["document_id"])
    case_file_available = bool(context.get("case_file_available"))
    return {
        "documentId": document_id,
        "title": str(context.get("title") or document_id),
        "caseFileAvailable": case_file_available,
        "caseFileName": str(context["case_file_name"]) if context.get("case_file_name") else None,
        "fileUrl": f"/v1/ui/cases/{case_id}/documents/{document_id}/file" if case_file_available else None,
        "sourceUrl": str(context["source_url"]) if context.get("source_url") else None,
        "downloadUrl": str(context["download_url"]) if context.get("download_url") else None,
        "viewerMimeType": str(context["viewer_mime_type"]) if context.get("viewer_mime_type") else None,
    }


def _consume_rate_limit(
    repo: LegalWorkspaceRepository,
    *,
    organization_id: str | None,
    user_id: str,
    policy: RateLimitPolicy,
) -> RateLimitResult:
    return repo.consume_rate_limit(
        organization_id=organization_id,
        user_id=user_id,
        route_key=policy.route_key,
        limit=policy.limit,
        window_seconds=policy.window_seconds,
    )


def _record_rate_limit_rejection(
    repo: LegalWorkspaceRepository,
    *,
    organization_id: str | None,
    case_id: str | None,
    user_id: str,
    result: RateLimitResult,
) -> None:
    try:
        repo.record_audit_event(
            organization_id=organization_id,
            case_id=case_id,
            user_id=user_id,
            event_type="api.rate_limit.exceeded",
            entity_type="api_route",
            entity_id=result.route_key,
            after_state={
                "route_key": result.route_key,
                "request_count": result.request_count,
                "limit": result.limit,
                "window_seconds": result.window_seconds,
                "window_started_at": result.window_started_at.isoformat(),
                "resets_at": result.resets_at.isoformat(),
            },
            metadata={
                "retry_after_seconds": result.retry_after_seconds,
            },
        )
    except Exception:
        METRICS.increment(
            "guardrail_audit_write_failures_total",
            event_type="api.rate_limit.exceeded",
            route_key=result.route_key,
        )


def _record_oversized_request_if_signed(
    *,
    request: Request,
    route_key: str,
    max_bytes: int,
    declared_size: int,
) -> None:
    try:
        auth = authenticate_auth_headers(
            method=request.method,
            path=request.url.path,
            query_string=request.url.query,
            user_id=request.headers.get(USER_HEADER),
            timestamp=request.headers.get(TIMESTAMP_HEADER),
            signature=request.headers.get(SIGNATURE_HEADER),
            body_sha256=request.headers.get(BODY_SHA256_HEADER),
        )
    except HTTPException:
        return

    try:
        with session_scope() as session:
            repo = LegalWorkspaceRepository(session)
            user_context = repo.user_context(auth.user_id)
            if user_context is None:
                return
            repo.record_audit_event(
                organization_id=user_context.organization_id,
                case_id=None,
                user_id=auth.user_id,
                event_type="api.request_body.too_large",
                entity_type="api_route",
                entity_id=route_key,
                after_state={
                    "route_key": route_key,
                    "declared_size": declared_size,
                    "max_bytes": max_bytes,
                },
                metadata={
                    "method": request.method.upper(),
                    "path": request.url.path,
                    "body_sha256": auth.body_sha256,
                },
            )
    except Exception:
        METRICS.increment(
            "guardrail_audit_write_failures_total",
            event_type="api.request_body.too_large",
            route_key=route_key,
        )
        return


def _raise_rate_limit_exceeded(result: RateLimitResult) -> None:
    METRICS.increment("guardrail_rate_limit_rejections_total", route_key=result.route_key)
    raise HTTPException(
        status_code=429,
        detail=f"Rate limit exceeded for {result.route_key}",
        headers={
            "Retry-After": str(result.retry_after_seconds),
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": result.resets_at.isoformat(),
        },
    )


def _route_metric_label(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    if request.url.path in SIGNED_POST_BODY_LIMITS:
        return request.url.path
    if request.url.path in {"/health", "/v1/operations/metrics", "/v1/audit/events"}:
        return request.url.path
    if request.url.path.startswith("/v1/cases/"):
        return "/v1/cases/{case_id}/..."
    if request.url.path.startswith("/v1/research/packs/"):
        return "/v1/research/packs/{pack_id}/..."
    return "unmatched"


def _require_research_pack_access_permission(
    repo: LegalWorkspaceRepository,
    *,
    pack_id: str,
    user_id: str,
    case_id: str | None = None,
    require_case_link: bool = False,
) -> str | None:
    access_context = repo.research_pack_access_context(pack_id)
    if access_context is None:
        raise HTTPException(status_code=404, detail=f"Research pack not found: {pack_id}")
    if not access_context.case_ids:
        if require_case_link:
            raise HTTPException(status_code=403, detail=f"Research pack is not linked to case: {pack_id}")
        return None
    if case_id is not None:
        if case_id not in set(access_context.case_ids):
            raise HTTPException(status_code=403, detail=f"Research pack is not linked to case: {case_id}")
        if not repo.user_has_case_permission(case_id=case_id, user_id=user_id):
            raise HTTPException(status_code=403, detail=f"User does not have permission on case: {user_id}")
        return case_id
    for case_id in access_context.case_ids:
        if repo.user_has_case_permission(case_id=case_id, user_id=user_id):
            return case_id
    raise HTTPException(status_code=403, detail=f"User does not have permission on research pack: {user_id}")


def _load_authorized_research_pack(
    repo: LegalWorkspaceRepository,
    *,
    pack_id: str,
    user_id: str,
    case_id: str | None,
    require_case_link: bool = False,
) -> LegalResearchPack:
    _require_research_pack_access_permission(
        repo,
        pack_id=pack_id,
        user_id=user_id,
        case_id=case_id,
        require_case_link=require_case_link,
    )
    try:
        pack = repo.load_research_pack(pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Research pack not found: {pack_id}")
    return pack


def _audit_organization_id(
    repo: LegalWorkspaceRepository,
    *,
    user_id: str,
    case_id: str | None,
) -> str | None:
    if case_id is not None:
        case_context = repo.case_context(case_id)
        if case_context is not None:
            return case_context.organization_id
    return _require_active_user(repo, user_id).organization_id


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decode_audit_cursor(cursor: str | None) -> tuple[datetime | None, int | None]:
    if cursor is None:
        return None, None
    cursor_value = cursor.strip()
    if not cursor_value:
        return None, None
    try:
        padded = cursor_value + "=" * (-len(cursor_value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        created_at = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        audit_event_id = int(data["audit_event_id"])
    except Exception as exc:
        raise HTTPException(status_code=422, detail="audit cursor is invalid") from exc
    if audit_event_id < 1:
        raise HTTPException(status_code=422, detail="audit cursor is invalid")
    return created_at, audit_event_id


def _encode_audit_cursor(event: dict[str, object]) -> str:
    created_at = event.get("created_at")
    if isinstance(created_at, datetime):
        created_at_value = created_at.isoformat()
    else:
        created_at_value = str(created_at)
    payload = json.dumps(
        {
            "created_at": created_at_value,
            "audit_event_id": int(event["audit_event_id"]),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _audit_page(events: list[dict[str, object]], limit: int) -> tuple[list[dict[str, object]], str | None]:
    page_events = events[:limit]
    if len(events) <= limit or not page_events:
        return page_events, None
    return page_events, _encode_audit_cursor(page_events[-1])


def _normalize_all_filter(value: str | None) -> str | None:
    if value is None:
        return None
    text_value = value.strip()
    if not text_value or text_value.lower() == "all":
        return None
    return text_value
