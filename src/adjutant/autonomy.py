"""Phase 5 limited automation: autonomy scorecards, promotion/demotion rules,
out-of-band approval bundles.

Pure and deterministic. The engine never changes an autonomy level itself —
it only computes recommendations from ledger-derived statistics, and a human
records any level change as an audited event. Promotion above shadow stays
disabled unless the high-privilege config flag is set.
"""

from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta
from typing import Literal

from .models import (
    ActionWindowStats,
    ApprovalRequest,
    AutonomyRecommendation,
    OobApprovalCreate,
    PolicyDecision,
)

AUTONOMY_VERSION = "autonomy-engine@1"
THRESHOLDS_VERSION = "autonomy-thresholds@1"
OOB_SIGNER_KEY_ID = "mock-oob-hmac-sha256-v1"
OOB_REQUEST_TTL_MINUTES = 30

# Documented, versioned thresholds. Changing them is a high-privilege config
# change; they are deliberately not environment-configurable.
WINDOW_DAYS = 30
MIN_PROPOSALS = 10
MIN_SIMULATED = 5
MIN_ALLOW_RATE_PCT = 80

AutonomyLevelValue = Literal["shadow", "suggest", "approve"]
LEVEL_ORDER: dict[str, int] = {"shadow": 0, "suggest": 1, "approve": 2}


def allow_rate_pct(stats: ActionWindowStats) -> int:
    if stats.proposals == 0:
        return 0
    return round(stats.allows * 100 / stats.proposals)


def evaluate_autonomy(
    stats: ActionWindowStats,
    current_level: AutonomyLevelValue = "shadow",
    *,
    now: datetime,
) -> AutonomyRecommendation:
    """Pure promotion/demotion rule evaluation for one action type.

    Promotion (shadow -> suggest -> approve) requires, over the window:
    enough proposals, enough simulated dry-runs, a high allow rate, and zero
    refusals or breaker trips. Demotion triggers, checked only when the
    current level is above shadow: any refusal drops one level; a breaker
    trip or a policy deny drops straight back to shadow.
    """
    promotion_reasons: list[str] = []
    hold_reasons: list[str] = []
    demotion_reasons: list[str] = []

    if stats.proposals >= MIN_PROPOSALS:
        promotion_reasons.append(
            f"{stats.proposals} proposals in window (minimum {MIN_PROPOSALS})"
        )
    else:
        hold_reasons.append(
            f"only {stats.proposals} proposals in window "
            f"(minimum {MIN_PROPOSALS})"
        )
    if stats.simulated >= MIN_SIMULATED:
        promotion_reasons.append(
            f"{stats.simulated} simulated dry-runs in window "
            f"(minimum {MIN_SIMULATED})"
        )
    else:
        hold_reasons.append(
            f"only {stats.simulated} simulated dry-runs in window "
            f"(minimum {MIN_SIMULATED})"
        )
    rate = allow_rate_pct(stats)
    if stats.proposals and rate >= MIN_ALLOW_RATE_PCT:
        promotion_reasons.append(
            f"allow rate {rate}% (minimum {MIN_ALLOW_RATE_PCT}%)"
        )
    else:
        hold_reasons.append(
            f"allow rate {rate}% below minimum {MIN_ALLOW_RATE_PCT}%"
        )

    if stats.refusals:
        demotion_reasons.append(
            f"{stats.refusals} refused execution(s) in window"
        )
    else:
        promotion_reasons.append("no refused executions in window")
    if stats.breaker_trips:
        demotion_reasons.append(
            f"{stats.breaker_trips} circuit breaker trip(s) in window"
        )
    else:
        promotion_reasons.append("no circuit breaker trips in window")
    if stats.denies:
        demotion_reasons.append(f"{stats.denies} policy deny in window")
    if stats.escalates:
        hold_reasons.append(
            f"{stats.escalates} escalation(s) in window need human judgement"
        )
    if stats.approvals_expired:
        hold_reasons.append(
            f"{stats.approvals_expired} approval(s) expired unused in window"
        )

    eligible = (
        not hold_reasons
        and not demotion_reasons
        and len(promotion_reasons) >= 5
    )

    target_level: AutonomyLevelValue = current_level
    if current_level != "shadow" and demotion_reasons:
        if stats.breaker_trips or stats.denies:
            target_level = "shadow"
            demotion_reasons.append("demoted to shadow")
        else:
            target_level = ["shadow", "suggest", "approve"][
                LEVEL_ORDER[current_level] - 1
            ]
            demotion_reasons.append(f"demoted to {target_level}")

    return AutonomyRecommendation(
        action_id=stats.action_id,
        current_level=current_level,
        eligible_for_promotion=eligible,
        promotion_reasons=promotion_reasons,
        hold_reasons=hold_reasons,
        demotion_reasons=demotion_reasons,
        demotion_target=target_level if target_level != current_level else None,
        thresholds_version=THRESHOLDS_VERSION,
        computed_at=now,
        engine=AUTONOMY_VERSION,
    )


def oob_bundle_payload(request: ApprovalRequest) -> dict:
    """Canonical dict that the out-of-band signature covers."""
    return {
        "id": str(request.id),
        "incident_id": str(request.incident_id),
        "proposal_id": str(request.proposal_id),
        "action_id": request.action_id,
        "action_hash": request.action_hash,
        "nonce": request.nonce,
        "topology": request.topology,
        "created_at": request.created_at.isoformat(),
        "expires_at": request.expires_at.isoformat(),
    }


def oob_canonical_json(request: ApprovalRequest) -> str:
    return json.dumps(oob_bundle_payload(request), sort_keys=True,
                      separators=(",", ":"))


def sign_oob_bundle(request: ApprovalRequest, key: str) -> str:
    digest = hmac.new(
        key.encode("utf-8"), oob_canonical_json(request).encode("utf-8"),
        "sha256",
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def verify_oob_approval(
    request: ApprovalRequest,
    data: OobApprovalCreate,
    decision: PolicyDecision,
    expected_action_hash: str,
    now: datetime,
    key: str,
) -> list[str]:
    """Fail-closed checks for an out-of-band approval submission."""
    reasons: list[str] = []
    if decision.decision != "allow":
        reasons.append(
            f"policy decision is '{decision.decision}'; out-of-band approval "
            "is only available for 'allow' proposals"
        )
    if request.status != "pending":
        reasons.append(
            f"approval request is '{request.status}'; only pending requests "
            "can be approved"
        )
    if request.expires_at <= now:
        reasons.append("approval request has expired")
    if request.action_hash != expected_action_hash:
        reasons.append(
            "proposal content has changed since the request was created "
            "(action hash mismatch)"
        )
    bundle_json = oob_canonical_json(request)
    expected = hmac.new(
        key.encode("utf-8"), bundle_json.encode("utf-8"), "sha256"
    ).hexdigest()
    provided = data.attestation_signature.removeprefix("hmac-sha256:")
    if not hmac.compare_digest(provided, expected):
        reasons.append(
            "out-of-band attestation signature does not verify against the "
            "request bundle"
        )
    return reasons


def approval_window_start(now: datetime) -> datetime:
    return now - timedelta(days=WINDOW_DAYS)
