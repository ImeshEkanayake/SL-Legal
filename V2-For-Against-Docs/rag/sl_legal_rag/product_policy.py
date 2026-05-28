from __future__ import annotations

import re
from dataclasses import dataclass
try:
    from enum import StrEnum
except ImportError:  # Python < 3.11 compatibility for local tooling.
    from enum import Enum

    class StrEnum(str, Enum):
        pass
from typing import Iterable

from .models import LegalResearchPack, StrategyDraftResponse, validate_claims_against_pack


class PolicyStatus(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW_REQUIRED = "review_required"


class LegalRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceReliabilityTier(StrEnum):
    OFFICIAL = "official"
    COURT_OR_TRIBUNAL = "court_or_tribunal"
    LICENSED_PUBLISHER = "licensed_publisher"
    SECONDARY = "secondary"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class PolicyViolation:
    code: str
    message: str
    severity: LegalRiskLevel


@dataclass(frozen=True)
class ReviewRequirement:
    lawyer_review_required: bool
    reviewer_role: str
    reason: str


@dataclass(frozen=True)
class PolicyEvaluation:
    status: PolicyStatus
    risk_level: LegalRiskLevel
    violations: tuple[PolicyViolation, ...]
    warnings: tuple[str, ...]
    review: ReviewRequirement

    @property
    def allowed(self) -> bool:
        return self.status != PolicyStatus.BLOCK


@dataclass(frozen=True)
class AuthorityPolicy:
    authority_level: int
    label: str
    requires_citation: bool = True


AUTHORITY_HIERARCHY: tuple[AuthorityPolicy, ...] = (
    AuthorityPolicy(1, "Constitution and binding official law"),
    AuthorityPolicy(2, "Acts, ordinances, regulations, gazettes, and other official legislation"),
    AuthorityPolicy(3, "Binding or persuasive reported court authority"),
    AuthorityPolicy(4, "Official practice directions, rules, circulars, and administrative materials"),
    AuthorityPolicy(5, "Licensed law reports, digests, and publisher materials"),
    AuthorityPolicy(6, "Secondary commentary and research aids"),
)


PROHIBITED_PATTERNS: tuple[tuple[str, str, str, LegalRiskLevel], ...] = (
    (
        "final_legal_advice",
        r"\b(final legal advice|definitive legal advice|you should definitely|you must file|guaranteed legal outcome)\b",
        "Output presents legal conclusions as final advice rather than lawyer-review draft work.",
        LegalRiskLevel.HIGH,
    ),
    (
        "guaranteed_outcome",
        r"\b(guaranteed to win|will definitely win|certain to succeed|court will certainly)\b",
        "Output guarantees a legal outcome.",
        LegalRiskLevel.HIGH,
    ),
    (
        "fabricate_authority",
        r"\b(fabricate|invent|make up|create fake)\b.{0,80}\b(citation|authority|case|evidence|document)\b",
        "Request or output asks to fabricate authority, evidence, or legal material.",
        LegalRiskLevel.CRITICAL,
    ),
    (
        "hide_adverse_authority",
        r"\b(hide|omit|conceal|suppress)\b.{0,80}\b(adverse authority|bad authority|unhelpful case|unfavorable case)\b",
        "Request or output asks to conceal adverse authority.",
        LegalRiskLevel.CRITICAL,
    ),
    (
        "obstruct_process",
        r"\b(destroy|backdate|tamper with|alter)\b.{0,80}\b(evidence|document|record|affidavit|filing)\b",
        "Request or output asks to obstruct legal process or tamper with records.",
        LegalRiskLevel.CRITICAL,
    ),
    (
        "bypass_lawyer_review",
        r"\b(skip|bypass|avoid)\b.{0,80}\b(lawyer review|legal review|human review)\b",
        "Request or output asks to bypass required lawyer review.",
        LegalRiskLevel.HIGH,
    ),
    (
        "prompt_injection",
        r"\b(ignore|disregard|override)\b.{0,80}\b(system|developer|previous instructions|pack boundary)\b|\b(use hidden knowledge|outside the pack|uncited answer)\b",
        "Request or output attempts to override the pack-bounded legal reasoning rules.",
        LegalRiskLevel.CRITICAL,
    ),
)


REQUEST_RISK_PATTERNS: tuple[tuple[str, LegalRiskLevel], ...] = (
    (r"\b(strategy|argument|counterargument|submission|petition|appeal|affidavit|draft|pleading)\b", LegalRiskLevel.HIGH),
    (r"\b(court|judge|tribunal|supreme court|court of appeal|high court)\b", LegalRiskLevel.HIGH),
    (r"\b(summarize|explain|compare|find|search)\b", LegalRiskLevel.MEDIUM),
)


def evaluate_text_policy(text: str) -> PolicyEvaluation:
    violations = tuple(_find_policy_violations(text))
    risk_level = _highest_risk([violation.severity for violation in violations] + [_request_risk_level(text)])
    status = PolicyStatus.BLOCK if violations else PolicyStatus.REVIEW_REQUIRED
    if not violations and risk_level == LegalRiskLevel.LOW:
        status = PolicyStatus.ALLOW
    return PolicyEvaluation(
        status=status,
        risk_level=risk_level,
        violations=violations,
        warnings=(),
        review=_review_requirement(risk_level),
    )


def evaluate_strategy_output_policy(
    *,
    response: StrategyDraftResponse,
    pack: LegalResearchPack,
    requested_output: str = "strategy_report",
) -> PolicyEvaluation:
    violations: list[PolicyViolation] = []
    warnings: list[str] = []
    combined_text = "\n".join(
        [
            requested_output,
            response.answer,
            "\n".join(claim.claim for claim in response.claims),
            "\n".join(item.counterargument for item in response.counterarguments),
            "\n".join(item.response for item in response.counterarguments),
            "\n".join(item.risk for item in response.risk_rankings),
            "\n".join(item.rationale for item in response.risk_rankings),
            "\n".join(item.query for item in response.next_retrieval_questions),
            "\n".join(response.missing_authorities),
            "\n".join(response.warnings),
        ]
    )
    violations.extend(_find_policy_violations(combined_text))

    for error in validate_claims_against_pack(response.claims, pack):
        violations.append(
            PolicyViolation(
                code="out_of_pack_citation",
                message=error,
                severity=LegalRiskLevel.CRITICAL,
            )
        )

    if response.pack_id != pack.pack_id:
        violations.append(
            PolicyViolation(
                code="pack_id_mismatch",
                message=f"response pack_id {response.pack_id!r} does not match requested pack_id {pack.pack_id!r}",
                severity=LegalRiskLevel.CRITICAL,
            )
        )

    if not pack.items:
        violations.append(
            PolicyViolation(
                code="empty_research_pack",
                message="Legal reasoning cannot proceed from an empty Legal Research Pack.",
                severity=LegalRiskLevel.CRITICAL,
            )
        )

    if not response.missing_authorities and pack.missing_source_summary:
        warnings.append("The pack has missing-source warnings; output should surface them for lawyer review.")

    source_warnings = source_reliability_warnings(pack)
    warnings.extend(source_warnings)

    risk_level = _highest_risk([violation.severity for violation in violations] + [_requested_output_risk(requested_output)])
    status = PolicyStatus.BLOCK if violations else PolicyStatus.REVIEW_REQUIRED
    return PolicyEvaluation(
        status=status,
        risk_level=risk_level,
        violations=tuple(violations),
        warnings=tuple(warnings),
        review=_review_requirement(risk_level),
    )


def source_reliability_tier(source_id: str, source_url: str | None = None) -> SourceReliabilityTier:
    source = source_id.strip().lower()
    url = (source_url or "").strip().lower()
    if source.startswith(("parl", "gov", "gazette", "printing", "lawnet", "constitution")):
        return SourceReliabilityTier.OFFICIAL
    if source.startswith(("supreme", "court", "coa", "sc_", "ca_", "tribunal")):
        return SourceReliabilityTier.COURT_OR_TRIBUNAL
    if "parliament.lk" in url or "documents.gov.lk" in url or "lawnet.gov.lk" in url:
        return SourceReliabilityTier.OFFICIAL
    if source.startswith(("lankalaw", "licensed", "nlr", "slr", "clr")):
        return SourceReliabilityTier.LICENSED_PUBLISHER
    if source.startswith(("commentary", "digest", "article", "book")):
        return SourceReliabilityTier.SECONDARY
    return SourceReliabilityTier.UNVERIFIED


def source_reliability_warnings(pack: LegalResearchPack) -> list[str]:
    warnings: list[str] = []
    if not pack.items:
        return ["Research pack has no cited source items."]
    tiers = [source_reliability_tier(item.source_id, item.source_url) for item in pack.items]
    if all(tier in {SourceReliabilityTier.SECONDARY, SourceReliabilityTier.UNVERIFIED} for tier in tiers):
        warnings.append("Research pack contains no official, court, or licensed primary/persuasive source.")
    if any(tier == SourceReliabilityTier.UNVERIFIED for tier in tiers):
        warnings.append("Research pack contains unverified source material that must be checked before use.")
    if any(item.authority_level >= 6 for item in pack.items):
        warnings.append("Research pack includes secondary material; legal claims still need primary authority support.")
    quality_flags = {
        str(flag)
        for item in pack.items
        for flag in (
            item.metadata.get("quality_flags")
            or item.metadata.get("source_quality_flags")
            or []
        )
    }
    blocking_quality_flags = {
        "empty_text",
        "unusable_ocr",
        "low_confidence_ocr",
        "low_ocr_confidence",
        "low_alphanumeric_ratio",
    }
    if quality_flags.intersection(blocking_quality_flags):
        warnings.append("Research pack includes extraction/OCR quality flags that must be reviewed before legal reliance.")
    if "translated_text_fallback" in quality_flags:
        warnings.append("Research pack includes translated fallback text; cite the original-language source and replace with official English text when available.")
    if "machine_translation_unreviewed" in quality_flags:
        warnings.append("Research pack includes unreviewed machine translation that needs lawyer review before legal reliance.")
    return warnings


def authority_label(authority_level: int) -> str:
    for policy in AUTHORITY_HIERARCHY:
        if policy.authority_level == authority_level:
            return policy.label
    return "Unclassified authority"


def require_policy_allowance(evaluation: PolicyEvaluation) -> None:
    if evaluation.status == PolicyStatus.BLOCK:
        detail = "; ".join(violation.message for violation in evaluation.violations)
        raise ValueError(f"Product policy blocked output: {detail}")


def _find_policy_violations(text: str) -> Iterable[PolicyViolation]:
    for code, pattern, message, severity in PROHIBITED_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            yield PolicyViolation(code=code, message=message, severity=severity)


def _request_risk_level(text: str) -> LegalRiskLevel:
    for pattern, risk in REQUEST_RISK_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return risk
    return LegalRiskLevel.LOW


def _requested_output_risk(requested_output: str) -> LegalRiskLevel:
    normalized = requested_output.replace("_", " ").lower()
    if any(term in normalized for term in ("submission", "petition", "affidavit", "strategy", "counterargument")):
        return LegalRiskLevel.HIGH
    if any(term in normalized for term in ("summary", "research", "memo")):
        return LegalRiskLevel.MEDIUM
    return LegalRiskLevel.LOW


def _highest_risk(levels: Iterable[LegalRiskLevel]) -> LegalRiskLevel:
    order = {
        LegalRiskLevel.LOW: 0,
        LegalRiskLevel.MEDIUM: 1,
        LegalRiskLevel.HIGH: 2,
        LegalRiskLevel.CRITICAL: 3,
    }
    return max(levels, key=lambda level: order[level])


def _review_requirement(risk_level: LegalRiskLevel) -> ReviewRequirement:
    if risk_level in {LegalRiskLevel.HIGH, LegalRiskLevel.CRITICAL}:
        return ReviewRequirement(
            lawyer_review_required=True,
            reviewer_role="qualified_lawyer",
            reason="High-risk legal work must be reviewed before use, filing, or client reliance.",
        )
    if risk_level == LegalRiskLevel.MEDIUM:
        return ReviewRequirement(
            lawyer_review_required=True,
            reviewer_role="lawyer_or_supervised_legal_reviewer",
            reason="Legal research outputs require supervised review before reliance.",
        )
    return ReviewRequirement(
        lawyer_review_required=False,
        reviewer_role="none",
        reason="Low-risk non-legal or administrative output.",
    )
