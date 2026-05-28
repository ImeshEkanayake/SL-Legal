from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_qdrant_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "load_rag_chunks_qdrant.py"
    spec = importlib.util.spec_from_file_location("load_rag_chunks_qdrant", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DummyModels:
    class MatchAny:
        def __init__(self, *, any):
            self.any = any

    class FieldCondition:
        def __init__(self, *, key, match):
            self.key = key
            self.match = match

    class Filter:
        def __init__(self, *, must):
            self.must = must

    class FilterSelector:
        def __init__(self, *, filter):
            self.filter = filter


class TimeoutClient:
    def __init__(self):
        self.calls = []

    def delete(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("result.status='wait_timeout'")


def test_delete_by_text_version_scope_uses_async_delete_and_tolerates_wait_timeout():
    module = load_qdrant_module()
    client = TimeoutClient()

    deleted = module.delete_by_text_version_scope(
        client,
        models_module=DummyModels,
        collection="chunks",
        text_version_ids=["tv1", "tv2"],
    )

    assert deleted == 1
    assert client.calls[0]["collection_name"] == "chunks"
    assert client.calls[0]["wait"] is False
