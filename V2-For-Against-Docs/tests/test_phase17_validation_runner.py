from __future__ import annotations

from scripts.run_phase17_lawyer_review_pack_validation import RetryingJsonChatClient, deterministic_reasoning_pack
from sl_legal_rag.models import LegalResearchPack, PackItem, QueryClass, RetrievalFilters
from sl_legal_rag.strategy import validate_strategy_response_against_pack


class FlakyJsonClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Azure OpenAI request failed with HTTP 500: transient")
        return {"ok": True}


class PermanentJsonClient:
    def complete_json(self, **_kwargs):
        raise RuntimeError("validation failed")


def test_retrying_json_chat_client_retries_transient_failures() -> None:
    client = FlakyJsonClient()
    retrying = RetryingJsonChatClient(client, attempts=2, retry_delay_seconds=0)

    assert retrying.complete_json(messages=[]) == {"ok": True}

    assert client.calls == 2
    assert retrying.attempt_log == [
        {
            "attempt": 1,
            "status": "fail",
            "transient": True,
            "error_type": "RuntimeError",
            "error": "Azure OpenAI request failed with HTTP 500: transient",
        },
        {"attempt": 2, "status": "pass"},
    ]


def test_retrying_json_chat_client_does_not_retry_non_transient_failures() -> None:
    retrying = RetryingJsonChatClient(PermanentJsonClient(), attempts=3, retry_delay_seconds=0)

    try:
        retrying.complete_json(messages=[])
    except RuntimeError as exc:
        assert str(exc) == "validation failed"
    else:
        raise AssertionError("expected RuntimeError")

    assert len(retrying.attempt_log) == 1
    assert retrying.attempt_log[0]["transient"] is False


def test_deterministic_reasoning_pack_stays_pack_bounded() -> None:
    pack = LegalResearchPack(
        pack_id="phase17_test_pack",
        query="trademark infringement and registration",
        query_class=QueryClass.STRATEGY,
        filters=RetrievalFilters(language="English"),
        retrieval_config={"source": "unit_test"},
        items=[
            PackItem(
                pack_item_id="phase17_test_item_001",
                chunk_id="chunk_001",
                document_id="act_ip_001",
                title="Code of Intellectual Property Act",
                document_type="Act",
                source_id="unit",
                authority_level=2,
                citation="Code of Intellectual Property Act",
                text="Trademark registration and enforcement provisions for testing.",
                fused_score=1.0,
                selection_reason="unit test",
                metadata={"authority_type": "Act", "authority_identifier": "Code of Intellectual Property Act"},
            ),
            PackItem(
                pack_item_id="phase17_test_item_002",
                chunk_id="chunk_002",
                document_id="gazette_001",
                title="Extraordinary Gazette 2146/37",
                document_type="Extraordinary Gazette",
                source_id="unit",
                authority_level=4,
                citation="Gazette No. 2146/37",
                text="Gazette material for testing.",
                fused_score=0.8,
                selection_reason="unit test",
                metadata={"authority_type": "Extraordinary Gazette", "authority_identifier": "Gazette No. 2146/37"},
            ),
            PackItem(
                pack_item_id="phase17_test_item_003",
                chunk_id="chunk_003",
                document_id="penal_001",
                title="Penal Code",
                document_type="Core Legislation",
                source_id="unit",
                authority_level=6,
                citation="Penal Code",
                text="Non-IP material for adverse retrieval testing.",
                fused_score=0.2,
                selection_reason="unit test",
                metadata={"authority_type": "Core Legislation", "authority_identifier": "Penal Code"},
            ),
        ],
    )

    draft = deterministic_reasoning_pack(
        {"case_id": "intellectual_property_trademark_infringement", "case_facts": "Trademark dispute"},
        pack,
        provider_error="Azure OpenAI request failed with HTTP 500",
    )

    assert draft.citation_validation["valid"] is True
    assert len(draft.reasoning_pack.for_against_brief) >= 2
    assert len(draft.reasoning_pack.missing_evidence_checklist) >= 5
    assert validate_strategy_response_against_pack(draft, pack, requested_output="lawyer_review_pack") == []
