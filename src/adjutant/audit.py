import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

GENESIS_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compute_event_hash(
    *,
    prev_hash: str,
    event_id: UUID,
    incident_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    source: str,
    recorded_at: datetime,
    valid_at: datetime | None,
    classification: str,
) -> str:
    material = "|".join(
        [
            prev_hash,
            str(event_id),
            str(incident_id),
            event_type,
            sha256_hex(canonical_json(payload)),
            source,
            recorded_at.isoformat(),
            valid_at.isoformat() if valid_at is not None else "",
            classification,
        ]
    )
    return sha256_hex(material)
