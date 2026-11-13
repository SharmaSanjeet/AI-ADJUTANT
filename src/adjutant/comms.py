from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from .models import (
    BriefAudience,
    BriefCheck,
    BriefClaim,
    BriefDraft,
    CheckIssue,
    CheckStatus,
    ClaimKind,
    Evidence,
    Fact,
    FactStatus,
    FactTrust,
)

CHECKER = "fact-checker@1"
MAX_VALUE_CHARS = 500
MAX_CLAIM_CHARS = 780

AUDIENCE_PREFIXES: dict[BriefAudience, tuple[str, ...] | None] = {
    BriefAudience.IC: None,
    BriefAudience.EXEC: ("asset/", "incident/", "decision/"),
    BriefAudience.TECHNICAL: ("alert/", "asset/", "identity/"),
    BriefAudience.LEGAL: ("regulatory/", "decision/", "identity/"),
}

AUDIENCE_LABELS: dict[BriefAudience, str] = {
    BriefAudience.IC: "Incident Commander",
    BriefAudience.EXEC: "Executive",
    BriefAudience.TECHNICAL: "Technical",
    BriefAudience.LEGAL: "Legal / Regulatory",
}

IDENTIFIER_RE = re.compile(
    r"\b(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+|"
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|"
    r"\d{1,3}(?:\.\d{1,3}){3})\b"
)
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"
    r"(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
NUMBER_RE = re.compile(r"(?<![\w.-])\d+(?:\.\d+)?(?![\w.-])")

NOT_CURRENT = {FactStatus.RETRACTED, FactStatus.SUPERSEDED}


def render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    except (TypeError, ValueError):
        return str(value)


def _claim_text(audience: BriefAudience, fact: Fact, value: str) -> str:
    stamp = fact.recorded_at.isoformat()
    if audience is BriefAudience.EXEC:
        text = f"Business-impact item {fact.attribute}: {value}. Recorded {stamp}."
    elif audience is BriefAudience.TECHNICAL:
        text = f"Technical observation {fact.attribute}: {value}. Recorded {stamp}."
    elif audience is BriefAudience.LEGAL:
        text = f"Regulatory item {fact.attribute}: {value}. Recorded {stamp}."
    else:
        text = f"{fact.attribute}: {value}. Recorded {stamp}."
    if fact.status is FactStatus.DISPUTED:
        text += " Status: disputed."
    return text


def build_claims(
    facts: list[Fact],
    audience: BriefAudience,
) -> list[BriefClaim]:
    """Build one fully-cited claim per eligible fact. No free-form model text."""
    prefixes = AUDIENCE_PREFIXES[audience]
    eligible = [
        fact
        for fact in facts
        if fact.trust is FactTrust.TRUSTED
        and fact.evidence
        and fact.status not in NOT_CURRENT
        and (prefixes is None or fact.attribute.startswith(prefixes))
    ]
    eligible.sort(key=lambda fact: (fact.recorded_at, fact.attribute))

    claims: list[BriefClaim] = []
    for fact in eligible:
        value = render_value(fact.value)
        if len(value) > MAX_VALUE_CHARS:
            continue
        text = _claim_text(audience, fact, value)
        if len(text) > MAX_CLAIM_CHARS:
            continue
        claims.append(
            BriefClaim(
                id=uuid4(),
                kind=ClaimKind.FACT,
                text=text,
                fact_ids=[fact.id],
                evidence_refs=[evidence.ref for evidence in fact.evidence],
            )
        )
    return claims


def _support_text(fact: Fact) -> str:
    parts = [fact.attribute, render_value(fact.value)]
    for evidence in fact.evidence:
        parts.append(evidence.ref)
        parts.append(evidence.content_hash)
        if evidence.excerpt:
            parts.append(evidence.excerpt)
    return "\n".join(parts)


def _retrieved_evidence(facts: list[Fact]) -> list[Evidence]:
    seen: dict[str, Evidence] = {}
    for fact in facts:
        for evidence in fact.evidence:
            seen.setdefault(evidence.ref, evidence)
    return list(seen.values())


def evaluate_brief(brief: BriefDraft, facts: dict[UUID, Fact]) -> BriefCheck:
    """Deterministic provenance gate. No model judgment is trusted here."""
    issues: list[CheckIssue] = []
    retrieved: list[Fact] = []
    has_judgment = False

    for claim in brief.claims:
        if claim.kind is ClaimKind.JUDGMENT:
            has_judgment = True

        if not claim.fact_ids:
            issues.append(
                CheckIssue(
                    code="provenance_missing",
                    claim_id=claim.id,
                    detail="claim has no fact references",
                )
            )
            continue

        cited: list[Fact] = []
        for fact_id in claim.fact_ids:
            fact = facts.get(fact_id)
            if fact is None:
                issues.append(
                    CheckIssue(
                        code="fact_not_found",
                        claim_id=claim.id,
                        detail=f"cited fact {fact_id} not found in incident",
                    )
                )
                continue
            cited.append(fact)
            retrieved.append(fact)
            if fact.status in NOT_CURRENT:
                issues.append(
                    CheckIssue(
                        code="fact_not_current",
                        claim_id=claim.id,
                        detail=f"fact {fact.attribute} is {fact.status.value}",
                    )
                )
            if fact.trust is not FactTrust.TRUSTED:
                issues.append(
                    CheckIssue(
                        code="trust_untrusted",
                        claim_id=claim.id,
                        detail=f"fact {fact.attribute} is {fact.trust.value}",
                    )
                )
            if not fact.evidence:
                issues.append(
                    CheckIssue(
                        code="evidence_missing",
                        claim_id=claim.id,
                        detail=f"fact {fact.attribute} has no evidence",
                    )
                )

        if not cited:
            continue

        known_refs = {e.ref for fact in cited for e in fact.evidence}
        for evidence_ref in claim.evidence_refs:
            if evidence_ref not in known_refs:
                issues.append(
                    CheckIssue(
                        code="evidence_unknown",
                        claim_id=claim.id,
                        detail=f"evidence {evidence_ref} not attached to cited facts",
                    )
                )

        support = "\n".join(_support_text(fact) for fact in cited)
        support_lower = support.lower()

        for token in set(IDENTIFIER_RE.findall(claim.text)) | set(
            UUID_RE.findall(claim.text)
        ):
            if token.lower() not in support_lower:
                issues.append(
                    CheckIssue(
                        code="identifier_unsupported",
                        claim_id=claim.id,
                        detail=f"identifier {token} does not appear in cited facts",
                    )
                )

        allowed_dates = {
            value.date().isoformat()
            for fact in cited
            for value in (fact.valid_at, fact.recorded_at)
        }
        for token in DATE_RE.findall(claim.text):
            if token not in allowed_dates:
                issues.append(
                    CheckIssue(
                        code="timestamp_unsupported",
                        claim_id=claim.id,
                        detail=f"timestamp {token} does not match cited facts",
                    )
                )

        allowed_numbers = set(
            NUMBER_RE.findall(TIMESTAMP_RE.sub(" ", DATE_RE.sub(" ", support)))
        )
        claim_for_numbers = TIMESTAMP_RE.sub(
            " ", DATE_RE.sub(" ", claim.text)
        )
        for token in NUMBER_RE.findall(claim_for_numbers):
            if token not in allowed_numbers:
                issues.append(
                    CheckIssue(
                        code="number_unsupported",
                        claim_id=claim.id,
                        detail=f"count {token} does not appear in cited facts",
                    )
                )

        if any(fact.status is FactStatus.DISPUTED for fact in cited) and (
            "disputed" not in claim.text.lower()
        ):
            issues.append(
                CheckIssue(
                    code="disputed_not_flagged",
                    claim_id=claim.id,
                    detail="claim cites a disputed fact without flagging it",
                )
            )

    if has_judgment:
        issues.append(
            CheckIssue(
                code="judgment_requires_review",
                detail="judgment claims require explicit human review",
            )
        )

    hard_issues = [
        issue for issue in issues if issue.code != "judgment_requires_review"
    ]
    if hard_issues:
        status = CheckStatus.FAILED
    elif has_judgment:
        status = CheckStatus.NEEDS_REVIEW
    else:
        status = CheckStatus.PASSED

    return BriefCheck(
        id=uuid4(),
        brief_id=brief.id,
        incident_id=brief.incident_id,
        status=status,
        issues=issues,
        claims_checked=len(brief.claims),
        evidence=_retrieved_evidence(retrieved),
        checked_at=datetime.now(tz=timezone.utc),
        checker=CHECKER,
    )
