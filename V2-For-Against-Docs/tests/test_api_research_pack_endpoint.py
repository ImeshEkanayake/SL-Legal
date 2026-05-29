from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from sl_legal_rag.auth import AUTH_SECRET_ENV, BODY_SHA256_HEADER, sign_auth_request
from sl_legal_rag.api import CASE_STRUCTURE_BODY_LIMIT_BYTES, app
from sl_legal_rag.metrics import METRICS
from sl_legal_rag.models import (
    AuthorityPackExpansionPlan,
    LegalResearchPack,
    PackItemSourceResponse,
    ResearchQueryRequest,
    StrategyDraftResponse,
)


TEST_AUTH_SECRET = "test-auth-secret-for-sl-legal-assist-32chars"


def json_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def signed_headers(
    monkeypatch,
    *,
    method: str,
    target: str,
    user_id: str = "user_1",
    body: bytes = b"",
    include_body_sha256: bool = False,
) -> dict[str, str]:
    monkeypatch.setenv(AUTH_SECRET_ENV, TEST_AUTH_SECRET)
    path, _, query_string = target.partition("?")
    timestamp = int(time.time())
    body_sha256 = hashlib.sha256(body).hexdigest()
    signature = sign_auth_request(
        method=method,
        path=path,
        query_string=query_string,
        user_id=user_id,
        timestamp=timestamp,
        body_sha256=body_sha256,
        secret=TEST_AUTH_SECRET,
    )
    headers = {
        "X-SL-Legal-User-ID": user_id,
        "X-SL-Legal-Auth-Timestamp": str(timestamp),
        "X-SL-Legal-Auth-Signature": signature,
    }
    if include_body_sha256:
        headers[BODY_SHA256_HEADER] = body_sha256
    return headers


def minimal_research_pack_payload() -> dict[str, object]:
    return {
        "pack_id": "pack_api_test",
        "query": "trade union bargaining",
        "query_class": "general_research",
        "filters": {},
        "retrieval_config": {"max_tokens": 12000},
        "items": [
            {
                "pack_item_id": "pack_api_test_item_001",
                "chunk_id": "chunk_1",
                "document_id": "doc_1",
                "title": "Industrial Disputes",
                "document_type": "Act",
                "source_id": "PARL_ACTS",
                "authority_level": 2,
                "citation": "Industrial Disputes Act",
                "text": "No employer shall refuse to bargain.",
                "fused_score": 1.0,
                "selection_reason": "test",
            }
        ],
    }


def _audit_event_fixture(audit_event_id: int, user_id: str, created_at: datetime) -> dict[str, object]:
    return {
        "audit_event_id": audit_event_id,
        "organization_id": "org_1",
        "case_id": None,
        "user_id": user_id,
        "event_type": "case.structure.generated",
        "entity_type": "case_structure",
        "entity_id": f"hash_{audit_event_id}",
        "before_state": {},
        "after_state": {"fact_count": 0},
        "metadata": {},
        "ip_address": None,
        "user_agent": None,
        "created_at": created_at,
    }


def allowed_rate_limit(route_key: str = "test.route") -> SimpleNamespace:
    return SimpleNamespace(
        allowed=True,
        route_key=route_key,
        request_count=1,
        limit=100,
        window_seconds=3600,
        window_started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        resets_at=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
        retry_after_seconds=3600,
    )


def metric_counter(snapshot: dict[str, object], name: str, **labels: str) -> int:
    counters = snapshot.get("counters", {})
    assert isinstance(counters, dict)
    entries = counters.get(name, [])
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, dict)
        entry_labels = entry.get("labels", {})
        if isinstance(entry_labels, dict) and all(entry_labels.get(key) == value for key, value in labels.items()):
            return int(entry["value"])
    return 0


def test_research_pack_endpoint_returns_typed_pack(monkeypatch):
    calls: dict[str, object] = {}

    def fake_create_research_pack(request: ResearchQueryRequest) -> LegalResearchPack:
        return LegalResearchPack.model_validate(
            {
                "pack_id": "pack_api_test",
                "query": request.query,
                "query_class": request.query_class,
                "filters": request.filters.model_dump(mode="json"),
                "retrieval_config": {"test": True},
                "items": [
                    {
                        "pack_item_id": "pack_api_test_item_001",
                        "chunk_id": "chunk_1",
                        "document_id": "doc_1",
                        "title": "Industrial Disputes",
                        "document_type": "Act",
                        "source_id": "PARL_ACTS",
                        "authority_level": 2,
                        "citation": "Industrial Disputes Act",
                        "text": "No employer shall refuse to bargain.",
                        "fused_score": 1.0,
                        "selection_reason": "test",
                    }
                ],
            }
        )

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def save_research_pack(self, **kwargs):
            assert kwargs["created_by_user_id"] == "user_1"
            return None

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.create_research_pack", fake_create_research_pack)
    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/research/packs"
    payload = {"query": "trade union bargaining", "max_pack_items": 3, "max_pack_tokens": 2000}
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["pack_id"] == "pack_api_test"
    assert data["items"][0]["pack_item_id"] == "pack_api_test_item_001"
    assert calls["audit_event"]["event_type"] == "research_pack.created"
    assert calls["audit_event"]["entity_id"] == "pack_api_test"
    assert calls["rate_limit"]["route_key"] == "research_pack.create"


def test_research_pack_endpoint_requires_signed_auth():
    response = TestClient(app).post(
        "/v1/research/packs",
        json={"query": "trade union bargaining", "max_pack_items": 3, "max_pack_tokens": 2000},
    )

    assert response.status_code == 401


def test_strategy_prompt_endpoint_requires_signed_auth():
    response = TestClient(app).post(
        "/v1/strategy/prompt",
        json={
            "case_facts": "The employer refused to bargain with the trade union.",
            "pack_id": "pack_api_test",
            "requested_output": "strategy_report",
        },
    )

    assert response.status_code == 401


def test_research_pack_expand_endpoint_links_parent_pack_and_case(monkeypatch):
    calls: dict[str, object] = {}

    def fake_create_research_pack(request: ResearchQueryRequest) -> LegalResearchPack:
        assert request.parent_pack_id == "pack_parent"
        assert request.case_id == "case_1"
        return LegalResearchPack.model_validate(
            {
                "pack_id": "pack_child",
                "query": request.query,
                "query_class": request.query_class,
                "filters": request.filters.model_dump(mode="json"),
                "retrieval_config": {
                    "fusion": "reciprocal_rank_fusion",
                    "max_tokens": request.max_pack_tokens,
                    "retriever_counts": {"opensearch_bm25_phrase_fuzzy": 1},
                },
                "items": [
                    {
                        "pack_item_id": "pack_child_item_001",
                        "chunk_id": "chunk_1",
                        "document_id": "doc_1",
                        "title": "Industrial Disputes",
                        "document_type": "Act",
                        "source_id": "PARL_ACTS",
                        "authority_level": 2,
                        "citation": "Industrial Disputes Act",
                        "text": "No employer shall refuse to bargain.",
                        "fused_score": 1.0,
                        "selection_reason": "test",
                    }
                ],
            }
        )

    class FakeRepository:
        def __init__(self, _session):
            pass

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_parent"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def next_child_research_pack_version(self, parent_pack_id: str):
            assert parent_pack_id == "pack_parent"
            return 4

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(organization_id="org_1", created_by_user_id="user_1")

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def save_research_pack(self, **kwargs):
            pack = kwargs["pack"]
            calls["saved_parent_pack_id"] = pack.parent_pack_id
            calls["saved_pack_version"] = pack.pack_version
            calls["saved_case_id"] = kwargs["case_id"]

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.create_research_pack", fake_create_research_pack)
    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/research/packs/pack_parent/expand"
    body = json_body({"query": "find adverse authority", "max_pack_items": 3, "max_pack_tokens": 2000})
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["parent_pack_id"] == "pack_parent"
    assert data["pack_version"] == 4
    assert data["pack_hash"]
    assert calls["saved_parent_pack_id"] == "pack_parent"
    assert calls["saved_pack_version"] == 4
    assert calls["saved_case_id"] == "case_1"
    assert calls["rate_limit"]["route_key"] == "research_pack.expand"
    assert calls["audit_event"]["after_state"]["parent_pack_id"] == "pack_parent"


def test_authority_pack_expansion_execute_endpoint_records_child_pack(monkeypatch):
    calls: dict[str, object] = {}
    plan = AuthorityPackExpansionPlan.model_validate(
        {
            "plan_id": "authplan_1",
            "case_id": "case_1",
            "draft_id": "draft_1",
            "review_item_id": "review_1",
            "parent_pack_id": "pack_parent",
            "candidate_ids": ["authcand_1"],
            "expansion_requests": [
                {
                    "query": "Supreme Court case-law on trademark confusion",
                    "query_class": "case_law_lookup",
                    "filters": {"require_official": True, "authority_levels": [1, 3]},
                    "max_pack_items": 4,
                    "max_pack_tokens": 3000,
                    "purpose": "authority_candidate_pack_expansion",
                }
            ],
        }
    )

    def fake_create_research_pack(request: ResearchQueryRequest) -> LegalResearchPack:
        calls["retrieval_request"] = request
        assert request.parent_pack_id == "pack_parent"
        assert request.case_id == "case_1"
        assert request.purpose == "authority_candidate_pack_expansion"
        return LegalResearchPack.model_validate(
            {
                "pack_id": "pack_child",
                "query": request.query,
                "query_class": request.query_class,
                "filters": request.filters.model_dump(mode="json"),
                "retrieval_config": {"max_tokens": request.max_pack_tokens},
                "items": [
                    {
                        "pack_item_id": "pack_child_item_001",
                        "chunk_id": "chunk_1",
                        "document_id": "doc_1",
                        "title": "Supreme Court Judgment",
                        "document_type": "judgment",
                        "source_id": "SC",
                        "authority_level": 3,
                        "citation": "SC Appeal No. 1/2020",
                        "text": "Confusion must be assessed by reference to the mark and market context.",
                        "fused_score": 1.0,
                        "selection_reason": "test",
                    }
                ],
            }
        )

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def get_authority_pack_expansion_plan(self, **kwargs):
            calls["loaded_plan"] = kwargs
            return plan

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_parent"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def next_child_research_pack_version(self, parent_pack_id: str):
            assert parent_pack_id == "pack_parent"
            return 2

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def save_research_pack(self, **kwargs):
            calls["saved_pack"] = kwargs

        def reserve_authority_pack_expansion_execution(self, **kwargs):
            calls["reservation"] = kwargs
            assert kwargs["reserved_by_user_id"] == "user_1"
            return plan

        def record_authority_pack_expansion_execution(self, **kwargs):
            calls["recorded_execution"] = kwargs
            assert kwargs["child_pack_id"] == "pack_child"
            assert kwargs["request_index"] == 0
            return AuthorityPackExpansionPlan.model_validate(
                {
                    **plan.model_dump(mode="json"),
                    "status": "executed",
                    "executed_pack_ids": ["pack_child"],
                    "execution_records": [
                        {
                            "request_index": 0,
                            "child_pack_id": "pack_child",
                            "child_pack_hash": kwargs["child_pack_hash"],
                            "item_count": kwargs["item_count"],
                            "executed_by_user_id": kwargs["executed_by_user_id"],
                            "executed_at": "2026-05-29T13:31:00",
                            "request_query_sha256": "b" * 64,
                        }
                    ],
                }
            )

        def record_audit_event(self, **kwargs):
            calls.setdefault("audit_events", []).append(kwargs)
            return len(calls["audit_events"])

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.create_research_pack", fake_create_research_pack)
    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/requests/0/execute"
    response = TestClient(app).post(
        target,
        headers=signed_headers(monkeypatch, method="POST", target=target),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["child_pack_id"] == "pack_child"
    assert data["authority_pack_expansion_plan"]["status"] == "executed"
    assert data["authority_pack_expansion_plan"]["citable"] is False
    assert calls["loaded_plan"]["draft_id"] == "draft_1"
    assert calls["rate_limit"]["route_key"] == "research_pack.expand"
    assert calls["saved_pack"]["purpose"] == "authority_candidate_pack_expansion"
    assert calls["reservation"]["request_index"] == 0
    assert calls["recorded_execution"]["executed_by_user_id"] == "user_1"
    assert calls["audit_events"][-1]["event_type"] == "authority_pack_expansion.executed"
    assert calls["audit_events"][-1]["after_state"]["citable"] is False


def test_authority_pack_expansion_execute_endpoint_reserves_before_retrieval(monkeypatch):
    calls: dict[str, object] = {}
    plan = AuthorityPackExpansionPlan.model_validate(
        {
            "plan_id": "authplan_1",
            "case_id": "case_1",
            "draft_id": "draft_1",
            "review_item_id": "review_1",
            "parent_pack_id": "pack_parent",
            "candidate_ids": ["authcand_1"],
            "expansion_requests": [
                {
                    "query": "Supreme Court case-law on trademark confusion",
                    "query_class": "case_law_lookup",
                    "filters": {"require_official": True, "authority_levels": [1, 3]},
                    "max_pack_items": 4,
                    "max_pack_tokens": 3000,
                    "purpose": "authority_candidate_pack_expansion",
                }
            ],
        }
    )

    def fake_create_research_pack(request: ResearchQueryRequest) -> LegalResearchPack:
        raise AssertionError("duplicate reservation must stop before retrieval")

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            return SimpleNamespace(organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            return True

        def get_authority_pack_expansion_plan(self, **kwargs):
            return plan

        def research_pack_access_context(self, pack_id: str):
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def next_child_research_pack_version(self, parent_pack_id: str):
            return 2

        def consume_rate_limit(self, **kwargs):
            return allowed_rate_limit(kwargs["route_key"])

        def save_research_pack(self, **kwargs):
            raise AssertionError("duplicate reservation must not save a child pack")

        def reserve_authority_pack_expansion_execution(self, **kwargs):
            calls["reservation"] = kwargs
            raise ValueError("Authority expansion request already reserved: 0")

        def record_authority_pack_expansion_execution(self, **kwargs):
            raise AssertionError("duplicate execution must not be recorded")

        def record_audit_event(self, **kwargs):
            calls.setdefault("audit_events", []).append(kwargs)
            return len(calls["audit_events"])

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.create_research_pack", fake_create_research_pack)
    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/cases/case_1/drafts/draft_1/authority-expansion-plans/authplan_1/requests/0/execute"
    response = TestClient(app).post(
        target,
        headers=signed_headers(monkeypatch, method="POST", target=target),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Authority expansion request already reserved: 0"
    assert calls["reservation"]["request_index"] == 0
    assert "audit_events" not in calls


def test_strategy_prompt_endpoint_returns_pack_bounded_messages_with_signed_auth(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=())

        def load_research_pack(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return LegalResearchPack.model_validate(minimal_research_pack_payload())

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/strategy/prompt"
    payload = {
        "case_facts": "The employer refused to bargain with the trade union.",
        "pack_id": "pack_api_test",
        "requested_output": "strategy_report",
    }
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["pack_id"] == "pack_api_test"
    assert "Legal Research Pack ID: pack_api_test" in data["messages"][1]["content"]
    assert "pack_api_test_item_001" in data["messages"][1]["content"]
    assert calls["audit_event"]["event_type"] == "strategy.prompt.built"
    assert calls["audit_event"]["metadata"]["case_facts_char_count"] == len(payload["case_facts"])
    assert calls["rate_limit"]["route_key"] == "strategy.prompt"


def test_strategy_prompt_endpoint_rejects_rate_limited_user(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def consume_rate_limit(self, **kwargs):
            assert kwargs["route_key"] == "strategy.prompt"
            return SimpleNamespace(
                allowed=False,
                route_key=kwargs["route_key"],
                request_count=121,
                limit=120,
                window_seconds=3600,
                window_started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                resets_at=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
                retry_after_seconds=60,
            )

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/strategy/prompt"
    payload = {
        "case_facts": "The employer refused to bargain with the trade union.",
        "pack_id": "pack_api_test",
        "requested_output": "strategy_report",
    }
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.headers["X-RateLimit-Limit"] == "120"
    assert calls["audit_event"]["event_type"] == "api.rate_limit.exceeded"
    assert calls["audit_event"]["entity_type"] == "api_route"
    assert calls["audit_event"]["entity_id"] == "strategy.prompt"
    assert calls["audit_event"]["after_state"]["request_count"] == 121


def test_case_structure_endpoint_requires_signed_auth():
    response = TestClient(app).post(
        "/v1/cases/structure",
        json={"raw_input": "The employer refused to bargain with the trade union."},
    )

    assert response.status_code == 401


def test_case_structure_endpoint_rejects_oversized_body(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            raise AssertionError("oversized body should be rejected before endpoint repository access")

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)

    target = "/v1/cases/structure"
    payload = {"raw_input": "x" * (CASE_STRUCTURE_BODY_LIMIT_BYTES + 1)}
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 413


def test_operations_metrics_endpoint_reports_guardrail_counts_and_latency(monkeypatch):
    METRICS.reset()

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    oversized_target = "/v1/cases/structure"
    oversized_body = json_body({"raw_input": "x" * (CASE_STRUCTURE_BODY_LIMIT_BYTES + 1)})
    oversized_response = TestClient(app).post(
        oversized_target,
        content=oversized_body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=oversized_target, body=oversized_body),
            "Content-Type": "application/json",
        },
    )
    assert oversized_response.status_code == 413

    metrics_target = "/v1/operations/metrics"
    metrics_response = TestClient(app).get(
        metrics_target,
        headers=signed_headers(monkeypatch, method="GET", target=metrics_target),
    )
    assert metrics_response.status_code == 200
    snapshot = metrics_response.json()
    assert metric_counter(snapshot, "guardrail_request_body_too_large_total", route_key="case.structure") == 1
    assert (
        metric_counter(
            snapshot,
            "http_request_errors_total",
            route="/v1/cases/structure",
            method="POST",
            status_code="413",
            status_class="4xx",
        )
        == 1
    )
    assert any(
        item["labels"] == {"method": "POST", "route": "/v1/cases/structure"} and item["count"] >= 1
        for item in snapshot["latencies"]
    )


def test_operations_metrics_prometheus_endpoint_accepts_bearer_token(monkeypatch):
    METRICS.reset()
    token = "metrics-token-for-production-scrape-32"
    monkeypatch.setenv("SL_LEGAL_METRICS_BEARER_TOKEN", token)

    METRICS.increment("guardrail_rate_limit_rejections_total", route_key="strategy.prompt")
    METRICS.observe_latency(12.345, route="/v1/strategy/prompt", method="POST")

    response = TestClient(app).get(
        "/v1/operations/metrics/prometheus",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# TYPE sl_legal_guardrail_rate_limit_rejections_total counter" in response.text
    assert 'sl_legal_guardrail_rate_limit_rejections_total{route_key="strategy.prompt"} 1' in response.text
    assert 'sl_legal_http_request_latency_ms_count{method="POST",route="/v1/strategy/prompt"} 1' in response.text
    assert 'sl_legal_http_request_latency_ms_sum{method="POST",route="/v1/strategy/prompt"} 12.345' in response.text


def test_operations_metrics_prometheus_endpoint_rejects_bad_bearer_token(monkeypatch):
    METRICS.reset()
    monkeypatch.setenv("SL_LEGAL_METRICS_BEARER_TOKEN", "metrics-token-for-production-scrape-32")

    response = TestClient(app).get(
        "/v1/operations/metrics/prometheus",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_case_structure_endpoint_audits_oversized_signed_body_hash(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/cases/structure"
    payload = {"raw_input": "x" * (CASE_STRUCTURE_BODY_LIMIT_BYTES + 1)}
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(
                monkeypatch,
                method="POST",
                target=target,
                body=body,
                include_body_sha256=True,
            ),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 413
    assert calls["audit_event"]["event_type"] == "api.request_body.too_large"
    assert calls["audit_event"]["entity_type"] == "api_route"
    assert calls["audit_event"]["entity_id"] == "case.structure"
    assert calls["audit_event"]["after_state"]["declared_size"] == len(body)
    assert calls["audit_event"]["after_state"]["max_bytes"] == CASE_STRUCTURE_BODY_LIMIT_BYTES
    assert calls["audit_event"]["metadata"]["body_sha256"] == hashlib.sha256(body).hexdigest()


def test_case_structure_endpoint_rejects_body_hash_mismatch(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            raise AssertionError("body hash mismatch should be rejected before endpoint repository access")

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)

    target = "/v1/cases/structure"
    body = json_body({"raw_input": "The employer refused to bargain."})
    wrong_body_sha256 = hashlib.sha256(b"not the request body").hexdigest()
    headers = signed_headers(monkeypatch, method="POST", target=target, body=body)
    headers[BODY_SHA256_HEADER] = wrong_body_sha256
    path, _, query_string = target.partition("?")
    headers["X-SL-Legal-Auth-Signature"] = sign_auth_request(
        method="POST",
        path=path,
        query_string=query_string,
        user_id="user_1",
        timestamp=int(headers["X-SL-Legal-Auth-Timestamp"]),
        body_sha256=wrong_body_sha256,
        secret=TEST_AUTH_SECRET,
    )
    response = TestClient(app).post(
        target,
        content=body,
        headers={**headers, "Content-Type": "application/json"},
    )

    assert response.status_code == 401


def test_strategy_prompt_rate_limit_audit_failure_is_counted(monkeypatch):
    METRICS.reset()

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def consume_rate_limit(self, **kwargs):
            return SimpleNamespace(
                allowed=False,
                route_key=kwargs["route_key"],
                request_count=121,
                limit=120,
                window_seconds=3600,
                window_started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
                resets_at=datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
                retry_after_seconds=60,
            )

        def record_audit_event(self, **_kwargs):
            raise RuntimeError("audit store unavailable")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/strategy/prompt"
    payload = {
        "case_facts": "The employer refused to bargain with the trade union.",
        "pack_id": "pack_api_test",
        "requested_output": "strategy_report",
    }
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 429
    snapshot = METRICS.snapshot()
    assert metric_counter(snapshot, "guardrail_rate_limit_rejections_total", route_key="strategy.prompt") == 1
    assert (
        metric_counter(
            snapshot,
            "guardrail_audit_write_failures_total",
            event_type="api.rate_limit.exceeded",
            route_key="strategy.prompt",
        )
        == 1
    )


def test_case_structure_endpoint_runs_only_after_signed_auth(monkeypatch):
    calls: dict[str, object] = {}

    class FakeStructure:
        raw_input_sha256 = "hash"
        facts: list[object] = []
        issues: list[object] = []
        timeline: list[object] = []
        retrieval_queries: list[object] = []
        warnings: list[object] = []

        def model_dump(self, **_kwargs):
            return {
                "schema_version": "mece_case_structure.v1",
                "source_id": "user_input",
                "raw_input_sha256": "hash",
                "case_summary": "Structured facts.",
                "parties": [],
                "facts": [],
                "timeline": [],
                "issues": [],
                "missing_information": [],
                "ambiguities": [],
                "contradictions": [],
                "retrieval_queries": [],
                "warnings": [],
            }

    def fake_generate_case_structure(**kwargs):
        calls["raw_input"] = kwargs["raw_input"]
        calls["max_completion_tokens"] = kwargs["max_completion_tokens"]
        return FakeStructure()

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.load_azure_chat_config", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("sl_legal_rag.api.AzureChatClient", lambda _config: object())
    monkeypatch.setattr("sl_legal_rag.api.generate_case_structure", fake_generate_case_structure)
    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/cases/structure"
    payload = {"raw_input": "The employer refused to bargain with the trade union."}
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json()["schema_version"] == "mece_case_structure.v1"
    assert calls["raw_input"] == payload["raw_input"]
    assert calls["audit_event"]["event_type"] == "case.structure.generated"
    assert calls["rate_limit"]["route_key"] == "case.structure"


def test_strategy_validate_endpoint_uses_stored_pack_items(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def research_pack_item_ids(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return ["pack_api_test_item_001"]

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/strategy/validate"
    payload = {
        "pack_id": "pack_api_test",
        "answer": "Supported. [pack_api_test_item_001]",
        "claims": [
            {
                "claim": "Supported claim",
                "pack_item_ids": ["pack_api_test_item_001"],
                "confidence": "needs_lawyer_review",
            }
        ],
    }
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"valid": True, "unknown_pack_item_ids": []}
    assert calls["audit_event"]["event_type"] == "strategy.validation.checked"
    assert calls["audit_event"]["after_state"]["valid"] is True
    assert calls["rate_limit"]["route_key"] == "strategy.validate"


def test_strategy_validate_endpoint_requires_signed_auth():
    response = TestClient(app).post(
        "/v1/strategy/validate",
        json={
            "pack_id": "pack_api_test",
            "answer": "Supported. [pack_api_test_item_001]",
            "claims": [
                {
                    "claim": "Supported claim",
                    "pack_item_ids": ["pack_api_test_item_001"],
                    "confidence": "needs_lawyer_review",
                }
            ],
        },
    )

    assert response.status_code == 401


def test_strategy_validate_endpoint_rejects_user_without_pack_case_permission(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            pass

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "outsider"
            return False

        def research_pack_item_ids(self, _pack_id: str):
            raise AssertionError("pack item IDs should not be loaded without case permission")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/strategy/validate"
    payload = {
        "pack_id": "pack_api_test",
        "answer": "Supported. [pack_api_test_item_001]",
        "claims": [
            {
                "claim": "Supported claim",
                "pack_item_ids": ["pack_api_test_item_001"],
                "confidence": "needs_lawyer_review",
            }
        ],
    }
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, user_id="outsider", body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 403


def test_pack_item_source_endpoint_returns_document_anchor(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def get_pack_item_source(self, *, pack_id: str, pack_item_id: str):
            assert pack_id == "pack_api_test"
            assert pack_item_id == "pack_api_test_item_001"
            return PackItemSourceResponse.model_validate(
                {
                    "pack_id": pack_id,
                    "pack_item_id": pack_item_id,
                    "chunk_id": "chunk_1",
                    "document_id": "doc_1",
                    "title": "Industrial Disputes",
                    "document_type": "Act",
                    "source_id": "PARL_ACTS",
                    "authority_level": 2,
                    "citation": "Industrial Disputes Act",
                    "page_start": 1,
                    "page_end": 3,
                    "selected_text": "No employer shall refuse to bargain.",
                    "context_text": "No employer shall refuse to bargain.",
                    "context_source": "research_pack_item",
                    "source_url": "https://example.test/doc",
                    "local_path": "data/raw/example.pdf",
                    "absolute_local_path": "/tmp/example.pdf",
                    "local_file_exists": False,
                    "page_text_available": False,
                    "source_quality_flags": [],
                    "retrieval_metadata": {"selection_reason": "exact_citation_provision rank 1"},
                }
            )

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/research/packs/pack_api_test/items/pack_api_test_item_001/source"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["pack_item_id"] == "pack_api_test_item_001"
    assert data["page_start"] == 1
    assert data["context_source"] == "research_pack_item"
    assert calls["audit_event"]["event_type"] == "research_pack.source.viewed"
    assert calls["audit_event"]["entity_id"] == "pack_api_test_item_001"


def test_pack_item_source_endpoint_requires_signed_auth():
    response = TestClient(app).get("/v1/research/packs/pack_api_test/items/pack_api_test_item_001/source")

    assert response.status_code == 401


def test_workspace_snapshot_endpoint_returns_case_ui_contract(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def case_workspace_snapshot(self, *, case_id: str, user_id: str):
            calls["snapshot"] = {"case_id": case_id, "user_id": user_id}
            return {
                "activeCaseId": case_id,
                "projects": [{"projectId": "project_1", "name": "Labour", "activeCaseCount": 1}],
                "cases": [
                    {
                        "caseId": case_id,
                        "projectId": "project_1",
                        "title": "Union Refusal Matter",
                        "court": "Supreme Court",
                        "matterType": "fundamental_rights",
                        "updatedAt": datetime(2026, 5, 24, tzinfo=timezone.utc),
                    }
                ],
                "messages": [
                    {
                        "messageId": "msg_1",
                        "threadId": "thread_1",
                        "role": "user",
                        "content": "Find cited authorities.",
                        "createdAt": datetime(2026, 5, 24, tzinfo=timezone.utc),
                    }
                ],
                "documents": [
                    {
                        "documentId": "doc_1",
                        "title": "Industrial Disputes Act",
                        "documentType": "Act",
                        "citation": "Industrial Disputes Act",
                        "sourceId": "PARL_ACTS",
                        "authorityLevel": 2,
                        "pageCount": 12,
                        "qualityFlags": [],
                        "textPreview": "No employer shall refuse to bargain.",
                    }
                ],
                "researchPackItems": [
                    {
                        "packItemId": "pack_1_item_001",
                        "packId": "pack_1",
                        "documentId": "doc_1",
                        "citation": "Industrial Disputes Act",
                        "title": "Industrial Disputes Act",
                        "authorityLevel": 2,
                        "fusedScore": 0.91,
                        "selectionReason": "exact citation",
                        "sourceWarnings": [],
                        "anchors": [
                            {
                                "anchorId": "anchor_1",
                                "pageNumber": 4,
                                "quote": "refuse to bargain",
                                "confidence": 0.96,
                            }
                        ],
                    }
                ],
                "drafts": [],
                "reviewItems": [],
            }

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/ui/cases/case_1/workspace"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["activeCaseId"] == "case_1"
    assert data["projects"][0]["activeCaseCount"] == 1
    assert data["researchPackItems"][0]["anchors"][0]["pageNumber"] == 4
    assert calls["snapshot"] == {"case_id": "case_1", "user_id": "user_1"}
    assert calls["audit_event"]["event_type"] == "case.workspace.viewed"


def test_workspace_document_file_endpoint_streams_authorized_case_file(monkeypatch, tmp_path):
    file_path = tmp_path / "industrial-disputes-act.pdf"
    file_path.write_bytes(b"%PDF-1.7\n% test legal document\n")
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def case_document_file_context(self, *, case_id: str, document_id: str):
            calls["file_context"] = {"case_id": case_id, "document_id": document_id}
            return {
                "document_id": document_id,
                "title": "Industrial Disputes Act",
                "case_file_available": True,
                "case_file_name": "doc_1_Industrial_Disputes_Act.pdf",
                "effective_file_path": str(file_path),
                "viewer_mime_type": "application/pdf",
                "source_url": None,
                "download_url": None,
            }

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/ui/cases/case_1/documents/doc_1/file"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-1.7")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert calls["file_context"] == {"case_id": "case_1", "document_id": "doc_1"}
    assert calls["audit_event"]["event_type"] == "case.document.file.viewed"


def test_workspace_document_cache_endpoint_caches_case_file(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def load_research_pack(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return pack

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def cache_case_document_file(self, *, case_id: str, document_id: str):
            calls["cache"] = {"case_id": case_id, "document_id": document_id}
            return {
                "document_id": document_id,
                "title": "Industrial Disputes Act",
                "case_file_available": True,
                "case_file_name": "doc_1_Industrial_Disputes_Act.pdf",
                "viewer_mime_type": "application/pdf",
                "source_url": "https://example.test/source",
                "download_url": "https://example.test/source.pdf",
            }

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/ui/cases/case_1/documents/doc_1/cache"
    response = TestClient(app).post(
        target,
        content=b"",
        headers=signed_headers(monkeypatch, method="POST", target=target, body=b""),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["documentId"] == "doc_1"
    assert data["caseFileAvailable"] is True
    assert data["fileUrl"] == "/v1/ui/cases/case_1/documents/doc_1/file"
    assert calls["rate_limit"]["route_key"] == "ui.document.cache"
    assert calls["cache"] == {"case_id": "case_1", "document_id": "doc_1"}
    assert calls["audit_event"]["event_type"] == "case.document.file.cached"


def test_workspace_document_status_endpoint_returns_current_document_state(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def case_workspace_document(self, *, case_id: str, document_id: str):
            calls["status"] = {"case_id": case_id, "document_id": document_id}
            return {
                "documentId": document_id,
                "title": "Industrial Disputes Act",
                "documentType": "Act",
                "citation": "Industrial Disputes Act, No. 43 of 1950",
                "sourceId": "PARL_ACTS",
                "authorityLevel": 2,
                "pageCount": 30,
                "qualityFlags": ["text_empty_needs_ocr"],
                "textPreview": "No employer shall refuse to bargain with a qualifying trade union.",
                "localPath": "data/raw/official/parliament/acts_pdfs/english/1950/043_industrial_disputes.pdf",
                "sourceUrl": "https://www.parliament.lk/en/business-of-parliament/act-details/G5240",
                "downloadUrl": "https://www.parliament.lk/uploads/acts/gbills/english/5240.pdf",
                "caseFileAvailable": True,
                "caseFileName": "doc_1_Industrial_Disputes_Act.pdf",
                "viewerMimeType": "application/pdf",
            }

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/ui/cases/case_1/documents/doc_1/status"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["documentId"] == "doc_1"
    assert data["caseFileAvailable"] is True
    assert data["textPreview"].startswith("No employer shall refuse")
    assert calls["status"] == {"case_id": "case_1", "document_id": "doc_1"}
    assert calls["audit_event"]["event_type"] == "case.document.status.viewed"


def test_workspace_chat_message_endpoint_persists_pack_bounded_user_and_assistant_messages(monkeypatch):
    calls: dict[str, object] = {}
    pack = LegalResearchPack.model_validate(minimal_research_pack_payload())

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def add_case_user_message(self, **kwargs):
            calls["message"] = kwargs
            return {
                "messageId": "msg_2",
                "threadId": "thread_1",
                "role": "user",
                "content": kwargs["content"],
                "createdAt": datetime(2026, 5, 24, tzinfo=timezone.utc),
                "packId": None,
            }

        def create_agent_run(self, **kwargs):
            calls["agent_run"] = kwargs
            return "agent_chat_1"

        def save_research_pack(self, **kwargs):
            calls["saved_pack"] = kwargs
            return SimpleNamespace(pack_id=kwargs["pack"].pack_id, item_count=len(kwargs["pack"].items), pack_hash="hash")

        def add_case_assistant_message(self, **kwargs):
            calls["assistant"] = kwargs
            return {
                "messageId": "msg_3",
                "threadId": kwargs["thread_id"],
                "role": "assistant",
                "content": kwargs["content"],
                "createdAt": datetime(2026, 5, 24, tzinfo=timezone.utc),
                "packId": kwargs["pack_id"],
            }

        def update_agent_run_status(self, **kwargs):
            calls["agent_status"] = kwargs

        def record_audit_event(self, **kwargs):
            calls.setdefault("audit_events", []).append(kwargs)
            return 1

    def fake_create_research_pack(request: ResearchQueryRequest) -> LegalResearchPack:
        calls["retrieval_request"] = request
        return pack

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)
    monkeypatch.setattr("sl_legal_rag.api.create_research_pack", fake_create_research_pack)

    target = "/v1/ui/cases/case_1/messages"
    payload = {"content": "Search for authority on unfair dismissal."}
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert [message["messageId"] for message in data["messages"]] == ["msg_2", "msg_3"]
    assert data["packId"] == "pack_api_test"
    assert data["retrievalStatus"] == "complete"
    assert calls["message"]["content"] == "Search for authority on unfair dismissal."
    assert calls["retrieval_request"].case_id == "case_1"
    assert calls["assistant"]["pack_id"] == "pack_api_test"
    assert calls["rate_limit"]["route_key"] == "ui.chat.message"
    assert calls["audit_events"][0]["event_type"] == "chat.message.created"
    assert calls["audit_events"][1]["event_type"] == "chat.assistant.created"


def test_workspace_case_create_endpoint_creates_case_for_active_user(monkeypatch):
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def create_case_for_user(self, **kwargs):
            calls["create_case"] = kwargs
            return SimpleNamespace(case_id="case_new", project_id="project_1")

        def record_audit_event(self, **kwargs):
            calls["audit_event"] = kwargs
            return 1

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/ui/cases"
    payload = {"title": "New Commercial Matter", "projectName": "Commercial Litigation"}
    body = json_body(payload)
    response = TestClient(app).post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"caseId": "case_new", "projectId": "project_1"}
    assert calls["create_case"]["project_name"] == "Commercial Litigation"
    assert calls["rate_limit"]["route_key"] == "ui.case.create"
    assert calls["audit_event"]["event_type"] == "case.created"


def test_workspace_snapshot_endpoint_requires_signed_auth():
    response = TestClient(app).get("/v1/ui/cases/case_1/workspace")

    assert response.status_code == 401


def test_pack_item_source_endpoint_rejects_user_without_pack_case_permission(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            pass

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "outsider"
            return False

        def get_pack_item_source(self, **_kwargs):
            raise AssertionError("source body should not be loaded without case permission")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/research/packs/pack_api_test/items/pack_api_test_item_001/source"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target, user_id="outsider"),
    )

    assert response.status_code == 403


def test_audit_events_endpoint_returns_authenticated_user_stream(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def user_has_organization_audit_access(self, *, organization_id: str, user_id: str):
            assert organization_id == "org_1"
            assert user_id == "user_1"
            return False

        def list_audit_events(self, **kwargs):
            calls.update(kwargs)
            return [
                {
                    "audit_event_id": 1,
                    "organization_id": "org_1",
                    "case_id": None,
                    "user_id": "user_1",
                    "event_type": "case.structure.generated",
                    "entity_type": "case_structure",
                    "entity_id": "hash",
                    "before_state": {},
                    "after_state": {"fact_count": 0},
                    "metadata": {"raw_input_char_count": 52},
                    "ip_address": None,
                    "user_agent": None,
                    "created_at": now,
                }
            ]

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/audit/events?event_type=case.structure.generated"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "user"
    assert data["user_id"] == "user_1"
    assert data["events"][0]["event_type"] == "case.structure.generated"
    assert calls["organization_id"] == "org_1"
    assert calls["user_id"] == "user_1"
    assert calls["event_type"] == "case.structure.generated"


def test_audit_events_endpoint_returns_next_cursor_and_accepts_cursor(monkeypatch):
    first_page_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    second_page_time = datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc)
    calls: list[dict[str, object]] = []

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def user_has_organization_audit_access(self, *, organization_id: str, user_id: str):
            assert organization_id == "org_1"
            assert user_id == "user_1"
            return False

        def list_audit_events(self, **kwargs):
            calls.append(kwargs)
            if kwargs["before_audit_event_id"] is None:
                return [
                    _audit_event_fixture(3, "user_1", first_page_time),
                    _audit_event_fixture(2, "user_1", first_page_time),
                    _audit_event_fixture(1, "user_1", second_page_time),
                ]
            assert kwargs["before_audit_event_id"] == 2
            assert kwargs["before_created_at"] == first_page_time
            return [_audit_event_fixture(1, "user_1", second_page_time)]

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    first_target = "/v1/audit/events?limit=2"
    first_response = TestClient(app).get(
        first_target,
        headers=signed_headers(monkeypatch, method="GET", target=first_target),
    )
    assert first_response.status_code == 200
    first_data = first_response.json()
    assert [event["audit_event_id"] for event in first_data["events"]] == [3, 2]
    assert first_data["next_cursor"]
    assert calls[0]["limit"] == 3

    second_target = f"/v1/audit/events?limit=2&cursor={first_data['next_cursor']}"
    second_response = TestClient(app).get(
        second_target,
        headers=signed_headers(monkeypatch, method="GET", target=second_target),
    )
    assert second_response.status_code == 200
    second_data = second_response.json()
    assert [event["audit_event_id"] for event in second_data["events"]] == [1]
    assert second_data["next_cursor"] is None


def test_audit_events_endpoint_rejects_other_user_without_organization_scope(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def user_has_organization_audit_access(self, **_kwargs):
            return False

        def list_audit_events(self, **_kwargs):
            raise AssertionError("audit rows should not be loaded for unauthorized user filter")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/audit/events?user_id=user_2"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 403


def test_audit_events_endpoint_allows_organization_scope_for_owner(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def user_has_organization_audit_access(self, *, organization_id: str, user_id: str):
            assert organization_id == "org_1"
            assert user_id == "user_1"
            return True

        def list_audit_events(self, **kwargs):
            calls.update(kwargs)
            return [
                {
                    "audit_event_id": 2,
                    "organization_id": "org_1",
                    "case_id": "case_1",
                    "user_id": "user_2",
                    "event_type": "research_pack.created",
                    "entity_type": "research_pack",
                    "entity_id": "pack_1",
                    "before_state": {},
                    "after_state": {"item_count": 1},
                    "metadata": {},
                    "ip_address": None,
                    "user_agent": None,
                    "created_at": now,
                }
            ]

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/audit/events?scope=organization&user_id=user_2"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "organization"
    assert data["user_id"] == "user_2"
    assert data["events"][0]["user_id"] == "user_2"
    assert calls["organization_id"] == "org_1"
    assert calls["user_id"] == "user_2"


def test_audit_events_endpoint_rejects_organization_scope_without_owner_access(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            pass

        def user_context(self, user_id: str):
            assert user_id == "user_1"
            return SimpleNamespace(user_id=user_id, organization_id="org_1")

        def user_has_organization_audit_access(self, *, organization_id: str, user_id: str):
            assert organization_id == "org_1"
            assert user_id == "user_1"
            return False

        def list_audit_events(self, **_kwargs):
            raise AssertionError("organization audit rows should not be loaded without audit access")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/audit/events?scope=organization"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target),
    )

    assert response.status_code == 403


def test_strategy_draft_endpoint_persists_reviewable_output(monkeypatch):
    pack = LegalResearchPack.model_validate(
        {
            "pack_id": "pack_api_test",
            "query": "trade union bargaining",
            "query_class": "statute_lookup",
            "filters": {},
            "retrieval_config": {"max_tokens": 12000},
            "items": [
                {
                    "pack_item_id": "pack_api_test_item_001",
                    "chunk_id": "chunk_1",
                    "document_id": "doc_1",
                    "title": "Industrial Disputes",
                    "document_type": "Act",
                    "source_id": "PARL_ACTS",
                    "authority_level": 2,
                    "citation": "Industrial Disputes Act",
                    "text": "No employer shall refuse to bargain.",
                    "fused_score": 1.0,
                    "selection_reason": "test",
                }
            ],
        }
    )
    generated = StrategyDraftResponse.model_validate(
        {
            "pack_id": pack.pack_id,
            "answer": "The argument is supported. [pack_api_test_item_001]",
            "claims": [
                {
                    "claim": "The argument is supported.",
                    "pack_item_ids": ["pack_api_test_item_001"],
                    "confidence": "needs_lawyer_review",
                }
            ],
            "missing_authorities": [],
            "warnings": ["Lawyer review required."],
        }
    )
    calls: dict[str, object] = {}

    class FakeConfig:
        deployment_name = "gpt-test"

    def fake_generate_strategy_draft(**kwargs):
        assert kwargs["pack"].pack_id == pack.pack_id
        return generated

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def research_pack_access_context(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return SimpleNamespace(pack_id=pack_id, case_ids=("case_1",))

        def load_research_pack(self, pack_id: str):
            assert pack_id == "pack_api_test"
            return pack

        def consume_rate_limit(self, **kwargs):
            calls["rate_limit"] = kwargs
            return allowed_rate_limit(kwargs["route_key"])

        def create_agent_run(self, **kwargs):
            calls["agent_input"] = kwargs["input_payload"]
            return "agent_1"

        def persist_strategy_draft(self, **kwargs):
            calls["persisted_case_id"] = kwargs["case_id"]
            assert kwargs["strategy_response"].claims[0].pack_item_ids == ["pack_api_test_item_001"]
            assert kwargs["agentic_research_plan"].schema_version == "agent_research_plan.v1"
            assert kwargs["matter_memory"].schema_version == "matter_memory.v1"
            return SimpleNamespace(
                draft_id="draft_1",
                message_id=None,
                agent_run_id="agent_1",
                claim_ids=["claim_1"],
                draft_review_item_id="review_draft_1",
                claim_review_item_ids=["review_claim_1"],
                reasoning_review_item_ids=[],
            )

        def update_agent_run_status(self, **kwargs):
            calls["agent_status"] = kwargs["status"]
            calls["agent_output"] = kwargs.get("output_payload")

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.load_azure_chat_config", lambda *_args, **_kwargs: FakeConfig())
    monkeypatch.setattr("sl_legal_rag.api.generate_strategy_draft", fake_generate_strategy_draft)
    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    draft_payload = {
        "case_id": "case_1",
        "case_facts": "The employer refused to bargain with the trade union.",
        "pack_id": pack.pack_id,
        "requested_output": "strategy_report",
    }
    draft_body = json_body(draft_payload)
    response = TestClient(app).post(
        "/v1/strategy/draft",
        content=draft_body,
        headers={
            **signed_headers(monkeypatch, method="POST", target="/v1/strategy/draft", body=draft_body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["draft_id"] == "draft_1"
    assert data["agent_run_id"] == "agent_1"
    assert data["claim_ids"] == ["claim_1"]
    assert data["draft_review_item_id"] == "review_draft_1"
    assert data["claim_review_item_ids"] == ["review_claim_1"]
    assert data["reasoning_review_item_ids"] == []
    assert calls["persisted_case_id"] == "case_1"
    assert calls["agent_status"] == "complete"
    assert calls["rate_limit"]["route_key"] == "strategy.draft"
    assert calls["agent_output"]["reasoning_pack_present"] is False
    assert calls["agent_output"]["agentic_research_plan"]["schema_version"] == "agent_research_plan.v1"
    assert calls["agent_output"]["matter_memory"]["schema_version"] == "matter_memory.v1"


def test_case_read_endpoints_return_reviewable_workflow(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    review_item = {
        "review_item_id": "review_1",
        "case_id": "case_1",
        "item_type": "draft",
        "item_id": "draft_1",
        "status": "pending",
        "priority": "normal",
        "assigned_to_user_id": "user_1",
        "reviewed_by_user_id": None,
        "decision": None,
        "comment": None,
        "due_at": None,
        "reviewed_at": None,
        "created_at": now,
        "updated_at": now,
        "item_title": "Strategy Report from pack_1",
        "item_excerpt": "Draft text.",
        "pack_id": "pack_1",
        "thread_id": "thread_1",
    }
    draft_summary = {
        "draft_id": "draft_1",
        "case_id": "case_1",
        "thread_id": "thread_1",
        "pack_id": "pack_1",
        "draft_type": "strategy_report",
        "title": "Strategy Report from pack_1",
        "status": "draft",
        "version": 1,
        "content_preview": "Draft text.",
        "claim_count": 1,
        "review_status": "pending",
        "created_by_agent_run_id": "agent_1",
        "created_by_user_id": "user_1",
        "created_at": now,
        "updated_at": now,
        "metadata": {},
    }
    claim_summary = {
        "claim_id": "claim_1",
        "case_id": "case_1",
        "thread_id": "thread_1",
        "message_id": "msg_1",
        "pack_id": "pack_1",
        "claim_text": "A cited legal claim.",
        "claim_type": "strategy_claim",
        "support_status": "supported",
        "risk_level": "unknown",
        "citation_count": 1,
        "review_status": "pending",
        "created_by_agent_run_id": "agent_1",
        "reviewed_by_user_id": None,
        "reviewed_at": None,
        "created_at": now,
        "updated_at": now,
        "metadata": {"draft_id": "draft_1"},
    }
    citation = {
        "pack_item_id": "pack_1_item_001",
        "citation_role": "support",
        "pack_id": "pack_1",
        "chunk_id": "chunk_1",
        "document_id": "doc_1",
        "title": "Industrial Disputes",
        "document_type": "Act",
        "source_id": "PARL_ACTS",
        "authority_level": 2,
        "year": 1950,
        "citation": "Industrial Disputes Act",
        "page_start": 1,
        "page_end": 2,
        "source_url": "https://example.test/doc",
        "local_path": "data/raw/doc.pdf",
        "anchor_count": 2,
        "source_endpoint": "/v1/research/packs/pack_1/items/pack_1_item_001/source",
    }

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def list_review_items(self, **kwargs):
            assert kwargs["case_id"] == "case_1"
            return [review_item]

        def list_case_drafts(self, **kwargs):
            assert kwargs["case_id"] == "case_1"
            return [draft_summary]

        def get_draft_detail(self, **kwargs):
            assert kwargs == {"case_id": "case_1", "draft_id": "draft_1"}
            return {**draft_summary, "content_markdown": "Draft text.", "claims": [claim_summary], "review_items": [review_item]}

        def list_case_claims(self, **kwargs):
            assert kwargs["case_id"] == "case_1"
            return [claim_summary]

        def get_claim_detail(self, **kwargs):
            assert kwargs == {"case_id": "case_1", "claim_id": "claim_1"}
            return {**claim_summary, "citations": [citation], "review_items": [review_item]}

        def list_case_audit_events(self, **kwargs):
            assert kwargs["case_id"] == "case_1"
            return [
                {
                    "audit_event_id": 7,
                    "organization_id": "org_1",
                    "case_id": "case_1",
                    "user_id": "user_1",
                    "event_type": "review.decision.recorded",
                    "entity_type": "review_item",
                    "entity_id": "review_1",
                    "before_state": {},
                    "after_state": {},
                    "metadata": {"decision": "approved"},
                    "ip_address": None,
                    "user_agent": None,
                    "created_at": now,
                }
            ]

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    client = TestClient(app)

    review_target = "/v1/cases/case_1/review/items"
    review_response = client.get(
        review_target,
        headers=signed_headers(monkeypatch, method="GET", target=review_target),
    )
    assert review_response.status_code == 200
    assert review_response.json()["items"][0]["review_item_id"] == "review_1"

    drafts_target = "/v1/cases/case_1/drafts"
    drafts_response = client.get(
        drafts_target,
        headers=signed_headers(monkeypatch, method="GET", target=drafts_target),
    )
    assert drafts_response.status_code == 200
    assert drafts_response.json()["drafts"][0]["draft_id"] == "draft_1"

    draft_target = "/v1/cases/case_1/drafts/draft_1"
    draft_response = client.get(
        draft_target,
        headers=signed_headers(monkeypatch, method="GET", target=draft_target),
    )
    assert draft_response.status_code == 200
    assert draft_response.json()["claims"][0]["claim_id"] == "claim_1"

    claims_target = "/v1/cases/case_1/claims?draft_id=draft_1"
    claims_response = client.get(
        claims_target,
        headers=signed_headers(monkeypatch, method="GET", target=claims_target),
    )
    assert claims_response.status_code == 200
    assert claims_response.json()["claims"][0]["citation_count"] == 1

    claim_target = "/v1/cases/case_1/claims/claim_1"
    claim_response = client.get(
        claim_target,
        headers=signed_headers(monkeypatch, method="GET", target=claim_target),
    )
    assert claim_response.status_code == 200
    assert claim_response.json()["citations"][0]["source_endpoint"].endswith("/source")

    audit_target = "/v1/cases/case_1/audit/events"
    audit_response = client.get(
        audit_target,
        headers=signed_headers(monkeypatch, method="GET", target=audit_target),
    )
    assert audit_response.status_code == 200
    assert audit_response.json()["events"][0]["event_type"] == "review.decision.recorded"


def test_review_decision_endpoint_records_audited_decision(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    review_item = {
        "review_item_id": "review_1",
        "case_id": "case_1",
        "item_type": "legal_claim",
        "item_id": "claim_1",
        "status": "approved",
        "priority": "normal",
        "assigned_to_user_id": "user_1",
        "reviewed_by_user_id": "user_1",
        "decision": "approved",
        "comment": "Reviewed against cited source.",
        "due_at": None,
        "reviewed_at": now,
        "created_at": now,
        "updated_at": now,
        "item_title": "A cited legal claim.",
        "item_excerpt": "A cited legal claim.",
        "pack_id": "pack_1",
        "thread_id": "thread_1",
    }
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def apply_review_decision(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(
                review_item=review_item,
                target_item_type="legal_claim",
                target_item_id="claim_1",
                target_status="lawyer_approved",
                audit_event_id=7,
            )

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    decision_target = "/v1/cases/case_1/review/items/review_1/decision"
    decision_payload = {
            "decision": "approved",
            "comment": "Reviewed against cited source.",
    }
    decision_body = json_body(decision_payload)
    response = TestClient(app).post(
        decision_target,
        content=decision_body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=decision_target, body=decision_body),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["review_item"]["status"] == "approved"
    assert data["target_status"] == "lawyer_approved"
    assert data["audit_event_id"] == 7
    assert calls["review_item_id"] == "review_1"
    assert calls["reviewer_user_id"] == "user_1"


def test_evidence_assessment_endpoints_return_grouped_stances(monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    created_assessment = {
        "schema_version": "claim_evidence_assessment.v1",
        "assessment_id": "assess_1",
        "case_id": "case_1",
        "claim_id": "claim_1",
        "claim_text": "The employer refused to bargain.",
        "pack_id": "pack_1",
        "pack_item_id": "pack_1_item_001",
        "stance": "contradicts_claim",
        "citation_role": "adverse",
        "rationale": "The source is adverse because it sets a qualification condition.",
        "confidence_score": 0.74,
        "risk_level": "high",
        "source_quote": "qualifying trade union",
        "page_start": 1,
        "page_end": 1,
        "review_status": "pending",
        "document_id": "doc_1",
        "title": "Industrial Disputes",
        "document_type": "Act",
        "source_id": "PARL_ACTS",
        "authority_level": 2,
        "year": 1950,
        "citation": "Industrial Disputes Act",
        "source_url": "https://example.test/doc",
        "local_path": "data/raw/doc.pdf",
        "anchor_count": 1,
        "source_endpoint": "/v1/research/packs/pack_1/items/pack_1_item_001/source",
        "metadata": {},
    }
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "user_1"
            return True

        def add_claim_evidence_assessment(self, **kwargs):
            calls["created"] = kwargs
            return created_assessment

        def grouped_claim_evidence_assessments(self, **kwargs):
            calls["grouped"] = kwargs
            return {
                "case_id": "case_1",
                "claim_id": None,
                "pack_id": "pack_1",
                "stance": None,
                "total_count": 1,
                "groups": [
                    {
                        "stance": "contradicts_claim",
                        "count": 1,
                        "items": [created_assessment],
                    }
                ],
            }

        def record_audit_event(self, **kwargs):
            calls["audit"] = kwargs
            return 11

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    client = TestClient(app)
    target = "/v1/cases/case_1/evidence/assessments"
    body = json_body(
        {
            "claim_text": "The employer refused to bargain.",
            "pack_id": "pack_1",
            "pack_item_id": "pack_1_item_001",
            "stance": "contradicts_claim",
            "rationale": "The source is adverse because it sets a qualification condition.",
            "confidence_score": 0.74,
            "risk_level": "high",
            "source_quote": "qualifying trade union",
            "page_start": 1,
            "page_end": 1,
            "metadata": {"fixture_time": now.isoformat()},
        }
    )
    create_response = client.post(
        target,
        content=body,
        headers={
            **signed_headers(monkeypatch, method="POST", target=target, body=body),
            "Content-Type": "application/json",
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["assessment"]["stance"] == "contradicts_claim"
    assert calls["audit"]["event_type"] == "evidence.assessment.recorded"
    assert calls["created"]["created_by_user_id"] == "user_1"

    list_target = "/v1/cases/case_1/evidence/assessments?pack_id=pack_1"
    list_response = client.get(
        list_target,
        headers=signed_headers(monkeypatch, method="GET", target=list_target),
    )
    assert list_response.status_code == 200
    assert list_response.json()["groups"][0]["items"][0]["citation_role"] == "adverse"
    assert calls["grouped"]["pack_id"] == "pack_1"


def test_case_read_endpoint_rejects_user_without_case_permission(monkeypatch):
    class FakeRepository:
        def __init__(self, _session):
            pass

        def case_context(self, case_id: str):
            assert case_id == "case_1"
            return SimpleNamespace(case_id=case_id, organization_id="org_1", created_by_user_id="user_1")

        def user_has_case_permission(self, *, case_id: str, user_id: str):
            assert case_id == "case_1"
            assert user_id == "outsider"
            return False

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr("sl_legal_rag.api.LegalWorkspaceRepository", FakeRepository)
    monkeypatch.setattr("sl_legal_rag.api.session_scope", fake_session_scope)

    target = "/v1/cases/case_1/drafts"
    response = TestClient(app).get(
        target,
        headers=signed_headers(monkeypatch, method="GET", target=target, user_id="outsider"),
    )

    assert response.status_code == 403


def test_case_read_endpoint_requires_valid_auth_signature(monkeypatch):
    target = "/v1/cases/case_1/drafts"

    missing_response = TestClient(app).get(target)
    assert missing_response.status_code == 401

    headers = signed_headers(monkeypatch, method="GET", target=target)
    headers["X-SL-Legal-Auth-Signature"] = "bad-signature"
    invalid_response = TestClient(app).get(target, headers=headers)
    assert invalid_response.status_code == 401
