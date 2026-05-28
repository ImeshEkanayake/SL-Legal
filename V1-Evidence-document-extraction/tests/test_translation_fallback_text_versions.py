from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path


def load_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "create_translation_fallback_text_versions.py"
    spec = importlib.util.spec_from_file_location("create_translation_fallback_text_versions", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_split_text_for_translation_preserves_paragraph_order():
    module = load_module()
    text = "first paragraph\n\nsecond paragraph is longer\n\nthird"

    chunks = module.split_text_for_translation(text, 30)

    assert chunks == ["first paragraph", "second paragraph is longer", "third"]
    assert "\n\n".join(chunks) == text


def test_translation_prompt_requires_complete_legal_translation():
    module = load_module()

    messages = module.build_translation_messages(
        source_language="Sinhala",
        target_language="English",
        chunk_text="source text",
        chunk_index=1,
        chunk_count=2,
    )

    combined = "\n".join(message["content"] for message in messages)
    assert "Do not summarize" in combined
    assert "Do not" in combined and "omit" in combined
    assert "Preserve section numbers" in combined
    assert "Return only the translated text" in combined


def test_translation_text_version_has_required_provenance():
    module = load_module()
    row = {
        "language": "Tamil",
        "source_page_count": 3,
        "source_text_version_id": "dtv_source",
    }
    translated = "Translated legal text"

    text_version = module.build_translation_text_version(
        row=row,
        translated_text=translated,
        target_language="English",
        translation_provider="azure_openai",
        translation_model="gpt-5.4-d7130e",
        translation_review_status="machine_draft",
        chunk_count=1,
    )

    assert text_version.text_origin == "translation"
    assert text_version.target_language == "English"
    assert text_version.source_language == "Tamil"
    assert text_version.translated_from_language == "Tamil"
    assert text_version.translation_provider == "azure_openai"
    assert text_version.translation_review_status == "machine_draft"
    assert text_version.source_text_version_id == "dtv_source"
    assert "translated_text_fallback" in text_version.quality_flags
    assert text_version.text_hash == hashlib.sha256(translated.encode("utf-8")).hexdigest()
