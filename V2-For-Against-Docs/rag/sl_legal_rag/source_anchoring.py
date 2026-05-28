from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PageText:
    page_id: str
    page_number: int
    text: str


@dataclass(frozen=True)
class SourceAnchor:
    anchor_id: str
    pack_id: str
    pack_item_id: str
    chunk_id: str
    document_id: str
    page_id: str | None
    page_number: int | None
    anchor_index: int
    char_start: int | None
    char_end: int | None
    quote: str
    match_method: str
    confidence: float
    metadata: dict[str, Any]


def stable_anchor_id(pack_item_id: str, anchor_index: int, quote: str) -> str:
    digest = hashlib.sha1(f"{pack_item_id}:{anchor_index}:{quote}".encode("utf-8")).hexdigest()[:16]
    return f"anchor_{pack_item_id}_{anchor_index:03d}_{digest}"


def combine_pages(pages: list[PageText]) -> tuple[str, list[tuple[int, int] | None]]:
    chars: list[str] = []
    mapping: list[tuple[int, int] | None] = []
    for page_index, page in enumerate(pages):
        if chars:
            chars.extend(["\n", "\n"])
            mapping.extend([None, None])
        for offset, char in enumerate(page.text):
            chars.append(char)
            mapping.append((page_index, offset))
    return "".join(chars), mapping


def normalize_with_mapping(text: str, mapping: list[tuple[int, int] | None] | None = None) -> tuple[str, list[tuple[int, int] | None]]:
    normalized_chars: list[str] = []
    normalized_mapping: list[tuple[int, int] | None] = []
    in_whitespace = False
    for index, char in enumerate(text):
        source_map = mapping[index] if mapping is not None else (0, index)
        if char.isspace():
            if not in_whitespace and normalized_chars:
                normalized_chars.append(" ")
                normalized_mapping.append(source_map)
            in_whitespace = True
            continue
        normalized_chars.append(char)
        normalized_mapping.append(source_map)
        in_whitespace = False
    while normalized_chars and normalized_chars[-1] == " ":
        normalized_chars.pop()
        normalized_mapping.pop()
    return "".join(normalized_chars), normalized_mapping


def anchors_from_context_match(
    *,
    pack_id: str,
    pack_item_id: str,
    chunk_id: str,
    document_id: str,
    pages: list[PageText],
    context_start: int,
    context_end: int,
    context_mapping: list[tuple[int, int] | None],
    match_method: str,
    confidence: float,
) -> list[SourceAnchor]:
    offsets_by_page: dict[int, list[int]] = {}
    for mapped in context_mapping[context_start:context_end]:
        if mapped is None:
            continue
        page_index, offset = mapped
        offsets_by_page.setdefault(page_index, []).append(offset)

    anchors: list[SourceAnchor] = []
    for page_index in sorted(offsets_by_page):
        page = pages[page_index]
        offsets = offsets_by_page[page_index]
        char_start = min(offsets)
        char_end = max(offsets) + 1
        quote = page.text[char_start:char_end]
        if not quote:
            continue
        anchor_index = len(anchors) + 1
        anchors.append(
            SourceAnchor(
                anchor_id=stable_anchor_id(pack_item_id, anchor_index, quote),
                pack_id=pack_id,
                pack_item_id=pack_item_id,
                chunk_id=chunk_id,
                document_id=document_id,
                page_id=page.page_id,
                page_number=page.page_number,
                anchor_index=anchor_index,
                char_start=char_start,
                char_end=char_end,
                quote=quote,
                match_method=match_method,
                confidence=confidence,
                metadata={"context_match": True},
            )
        )
    return anchors


def build_source_anchors(
    *,
    pack_id: str,
    pack_item_id: str,
    chunk_id: str,
    document_id: str,
    selected_text: str,
    pages: list[PageText],
) -> list[SourceAnchor]:
    selected = selected_text.strip()
    if not selected or not pages:
        return []

    context, context_mapping = combine_pages(pages)
    exact_start = context.find(selected)
    if exact_start >= 0:
        return anchors_from_context_match(
            pack_id=pack_id,
            pack_item_id=pack_item_id,
            chunk_id=chunk_id,
            document_id=document_id,
            pages=pages,
            context_start=exact_start,
            context_end=exact_start + len(selected),
            context_mapping=context_mapping,
            match_method="exact_context",
            confidence=1.0,
        )

    for page in pages:
        page_start = page.text.find(selected)
        if page_start >= 0:
            return anchors_from_context_match(
                pack_id=pack_id,
                pack_item_id=pack_item_id,
                chunk_id=chunk_id,
                document_id=document_id,
                pages=[page],
                context_start=page_start,
                context_end=page_start + len(selected),
                context_mapping=[(0, offset) for offset in range(len(page.text))],
                match_method="exact_page",
                confidence=1.0,
            )

    normalized_context, normalized_mapping = normalize_with_mapping(context, context_mapping)
    normalized_selected = WHITESPACE_RE.sub(" ", selected).strip()
    normalized_start = normalized_context.find(normalized_selected)
    if normalized_start >= 0:
        return anchors_from_context_match(
            pack_id=pack_id,
            pack_item_id=pack_item_id,
            chunk_id=chunk_id,
            document_id=document_id,
            pages=pages,
            context_start=normalized_start,
            context_end=normalized_start + len(normalized_selected),
            context_mapping=normalized_mapping,
            match_method="normalized_context",
            confidence=0.95,
        )

    for page in pages:
        normalized_page, normalized_page_mapping = normalize_with_mapping(page.text)
        page_start = normalized_page.find(normalized_selected)
        if page_start >= 0:
            return anchors_from_context_match(
                pack_id=pack_id,
                pack_item_id=pack_item_id,
                chunk_id=chunk_id,
                document_id=document_id,
                pages=[page],
                context_start=page_start,
                context_end=page_start + len(normalized_selected),
                context_mapping=normalized_page_mapping,
                match_method="normalized_page",
                confidence=0.95,
            )

    return []
