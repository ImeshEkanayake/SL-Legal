from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Create compact, sortable-enough application IDs with explicit type prefixes."""

    clean_prefix = prefix.strip().lower().replace("-", "_")
    if not clean_prefix:
        raise ValueError("id prefix is required")
    return f"{clean_prefix}_{uuid.uuid4().hex}"
