from __future__ import annotations

from dataclasses import dataclass
try:
    from enum import StrEnum
except ImportError:  # Python < 3.11 compatibility for local tooling.
    from enum import Enum

    class StrEnum(str, Enum):
        pass


class OcrConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNUSABLE = "unusable"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExtractionQualityDecision:
    text_length: int
    confidence: float | None
    confidence_band: OcrConfidenceBand
    quality_score: float
    quality_flags: tuple[str, ...]
    legal_answer_eligible: bool
    requires_manual_review: bool


@dataclass(frozen=True)
class DocumentExtractionQuality:
    page_count: int
    eligible_page_count: int
    blocked_page_count: int
    average_quality_score: float
    quality_flags: tuple[str, ...]
    legal_answer_eligible: bool
    requires_manual_review: bool


def confidence_band(confidence: float | None) -> OcrConfidenceBand:
    if confidence is None:
        return OcrConfidenceBand.UNKNOWN
    if confidence >= 0.95:
        return OcrConfidenceBand.HIGH
    if confidence >= 0.85:
        return OcrConfidenceBand.MEDIUM
    if confidence >= 0.70:
        return OcrConfidenceBand.LOW
    return OcrConfidenceBand.UNUSABLE


def evaluate_extracted_text(
    text: str,
    *,
    extraction_method: str,
    ocr_confidence: float | None = None,
) -> ExtractionQualityDecision:
    normalized_text = text.strip()
    flags: list[str] = []
    band = confidence_band(ocr_confidence)
    if not normalized_text:
        flags.append("empty_text")
    if len(normalized_text) < 80:
        flags.append("very_short_text")
    if "\ufffd" in normalized_text:
        flags.append("replacement_characters")

    alnum_ratio = _alnum_ratio(normalized_text)
    if normalized_text and alnum_ratio < 0.35:
        flags.append("low_alphanumeric_ratio")

    method = extraction_method.strip().lower()
    if "ocr" in method:
        if band == OcrConfidenceBand.UNUSABLE:
            flags.append("unusable_ocr")
        elif band == OcrConfidenceBand.LOW:
            flags.append("low_confidence_ocr")
        elif band == OcrConfidenceBand.UNKNOWN:
            flags.append("unknown_ocr_confidence")

    quality_score = _quality_score(
        text_length=len(normalized_text),
        alnum_ratio=alnum_ratio,
        confidence=ocr_confidence,
        flags=flags,
    )
    blocking_flags = {"empty_text", "unusable_ocr", "low_confidence_ocr", "low_alphanumeric_ratio"}
    legal_answer_eligible = not any(flag in blocking_flags for flag in flags)
    review_flags = {"very_short_text", "replacement_characters", "unknown_ocr_confidence"}
    requires_manual_review = not legal_answer_eligible or any(flag in review_flags for flag in flags)
    return ExtractionQualityDecision(
        text_length=len(normalized_text),
        confidence=ocr_confidence,
        confidence_band=band,
        quality_score=quality_score,
        quality_flags=tuple(sorted(set(flags))),
        legal_answer_eligible=legal_answer_eligible,
        requires_manual_review=requires_manual_review,
    )


def aggregate_document_quality(page_decisions: list[ExtractionQualityDecision]) -> DocumentExtractionQuality:
    if not page_decisions:
        return DocumentExtractionQuality(
            page_count=0,
            eligible_page_count=0,
            blocked_page_count=0,
            average_quality_score=0.0,
            quality_flags=("empty_document",),
            legal_answer_eligible=False,
            requires_manual_review=True,
        )
    flags = sorted({flag for decision in page_decisions for flag in decision.quality_flags})
    eligible_page_count = sum(1 for decision in page_decisions if decision.legal_answer_eligible)
    blocked_page_count = len(page_decisions) - eligible_page_count
    average_quality_score = round(sum(decision.quality_score for decision in page_decisions) / len(page_decisions), 4)
    return DocumentExtractionQuality(
        page_count=len(page_decisions),
        eligible_page_count=eligible_page_count,
        blocked_page_count=blocked_page_count,
        average_quality_score=average_quality_score,
        quality_flags=tuple(flags),
        legal_answer_eligible=blocked_page_count == 0,
        requires_manual_review=blocked_page_count > 0 or any(decision.requires_manual_review for decision in page_decisions),
    )


def _alnum_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for char in text if char.isalnum()) / len(text)


def _quality_score(
    *,
    text_length: int,
    alnum_ratio: float,
    confidence: float | None,
    flags: list[str],
) -> float:
    length_score = min(1.0, text_length / 500)
    confidence_score = confidence if confidence is not None else 0.75
    raw_score = (length_score * 0.25) + (alnum_ratio * 0.25) + (confidence_score * 0.50)
    penalty = 0.15 * len(flags)
    return round(max(0.0, min(1.0, raw_score - penalty)), 4)
