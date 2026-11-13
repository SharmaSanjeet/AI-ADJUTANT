from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from .models import ClockComputation


@dataclass(frozen=True)
class ClockRule:
    regime: str
    label: str
    description: str
    hours: int | None = None
    business_days: int | None = None
    calendar: str = "calendar"
    timezone: str | None = None


CLOCK_RULES: dict[str, ClockRule] = {
    "cert-in-6h": ClockRule(
        regime="cert-in-6h",
        label="CERT-In reporting (6 hours)",
        description=(
            "Indian CERT-In directions require reporting certain incidents "
            "within 6 hours of noticing. Candidate only until legal confirms."
        ),
        hours=6,
        calendar="calendar",
        timezone="Asia/Kolkata",
    ),
    "gdpr-72h": ClockRule(
        regime="gdpr-72h",
        label="GDPR breach notification (72 hours)",
        description=(
            "GDPR Article 33 requires notifying the supervisory authority "
            "within 72 hours of awareness. Legal must confirm applicability."
        ),
        hours=72,
        calendar="calendar",
        timezone="Europe/Brussels",
    ),
    "sec-4-business-days": ClockRule(
        regime="sec-4-business-days",
        label="SEC material incident (4 business days)",
        description=(
            "SEC Form 8-K Item 1.05 requires filing within four business days "
            "of determining materiality. Calendar is configurable."
        ),
        business_days=4,
        calendar="business",
        timezone="America/New_York",
    ),
    "hipaa-60-days": ClockRule(
        regime="hipaa-60-days",
        label="HIPAA breach notification (60 days)",
        description=(
            "HIPAA requires individual notification within 60 days of "
            "discovery. Applicability requires legal confirmation."
        ),
        hours=60 * 24,
        calendar="calendar",
        timezone="America/New_York",
    ),
}


def get_clock_rule(regime: str) -> ClockRule:
    try:
        return CLOCK_RULES[regime]
    except KeyError as exc:
        raise ValueError(f"unknown clock regime: {regime}") from exc


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_holidays(holidays: list[date | str]) -> list[str]:
    result = []
    for holiday in holidays:
        if isinstance(holiday, date):
            result.append(holiday.isoformat())
        else:
            result.append(str(holiday))
    return sorted(set(result))


def add_business_days(
    start: datetime,
    days: int,
    timezone_name: str,
    holidays: list[str],
) -> tuple[datetime, list[str]]:
    zone = ZoneInfo(timezone_name)
    cursor = _to_utc(start).astimezone(zone)
    steps: list[str] = []
    counted = 0
    holiday_set = set(holidays)

    while counted < days:
        cursor = cursor + timedelta(days=1)
        day = cursor.date().isoformat()
        if cursor.weekday() >= 5:
            steps.append(f"skip {day} (weekend)")
            continue
        if day in holiday_set:
            steps.append(f"skip {day} (holiday)")
            continue
        counted += 1
        steps.append(f"count {day} (business day {counted}/{days})")

    return cursor.astimezone(timezone.utc), steps


def compute_clock(
    rule: ClockRule,
    trigger_at: datetime,
    *,
    holidays: list[date | str] | None = None,
    computed_at: datetime | None = None,
) -> ClockComputation:
    """Deterministic deadline computation with a full, auditable trace."""
    trigger = _to_utc(trigger_at)
    holiday_list = _iso_holidays(list(holidays or []))
    now = _to_utc(computed_at or datetime.now(tz=timezone.utc))

    steps = [
        f"rule={rule.regime} ({rule.label})",
        f"trigger={trigger.isoformat()}",
        f"calendar={rule.calendar}"
        + (f" timezone={rule.timezone}" if rule.timezone else ""),
    ]

    if rule.hours is not None:
        due = trigger + timedelta(hours=rule.hours)
        duration = f"{rule.hours} hours"
        steps.append(f"add {rule.hours} calendar hours")
    elif rule.business_days is not None:
        assert rule.timezone is not None
        due, day_steps = add_business_days(
            trigger, rule.business_days, rule.timezone, holiday_list
        )
        duration = f"{rule.business_days} business days"
        steps.extend(day_steps)
    else:
        raise ValueError(f"clock rule {rule.regime} has no duration")

    steps.append(f"due={due.isoformat()}")
    steps.append("engine=clock-engine@1")

    return ClockComputation(
        id=uuid4(),
        regime=rule.regime,
        label=rule.label,
        trigger_at=trigger,
        due_at=due,
        duration=duration,
        calendar=rule.calendar,  # type: ignore[arg-type]
        timezone=rule.timezone,
        holidays=holiday_list,
        steps=steps,
        computed_at=now,
    )
