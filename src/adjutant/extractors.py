"""Quarantine boundary: raw, attacker-controlled text becomes typed fields here.

Deterministic parsers run first. The LLM extractor only sees residual unstructured
text, has no tools, and must return the strict ExtractedSignal schema.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .models import Confidence
from .ports.model import ExtractedSignal, ModelPort

ALLOWED_KEYS = {"host", "user", "process", "action", "severity", "message"}
MAX_FIELDS = 10
MAX_VALUE_LENGTH = 500


class ExtractedField(BaseModel):
    attribute: str
    value: Any
    confidence: Confidence
    extractor: str


def _scalar(value: Any) -> str | None:
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:MAX_VALUE_LENGTH]
    return None


def deterministic_extract(kind: str, content: str) -> list[ExtractedField]:
    fields: list[ExtractedField] = []

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        for key in ALLOWED_KEYS:
            if key not in parsed:
                continue
            value = _scalar(parsed[key])
            if value is None:
                continue
            fields.append(
                ExtractedField(
                    attribute=f"signal/{kind}/{key}",
                    value=value,
                    confidence=Confidence(
                        source_reliability=0.9,
                        corroboration=1,
                        extraction_certainty=0.95,
                    ),
                    extractor="deterministic",
                )
            )
        if fields:
            return fields[:MAX_FIELDS]

    pairs: dict[str, str] = {}
    for token in content.replace(",", " ").split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        normalized = key.strip().lower()
        if normalized in ALLOWED_KEYS and value.strip():
            pairs[normalized] = value.strip()[:MAX_VALUE_LENGTH]

    for key, value in pairs.items():
        fields.append(
            ExtractedField(
                attribute=f"signal/{kind}/{key}",
                value=value,
                confidence=Confidence(
                    source_reliability=0.8,
                    corroboration=0,
                    extraction_certainty=0.9,
                ),
                extractor="deterministic",
            )
        )

    return fields[:MAX_FIELDS]


async def llm_extract(
    model: ModelPort, kind: str, content: str
) -> list[ExtractedField]:
    extracted = await model.extract(content, ExtractedSignal)
    if not isinstance(extracted, ExtractedSignal):
        raise TypeError("ModelPort.extract returned the wrong schema")

    if not extracted.summary.strip() and not extracted.entities:
        return []

    confidence = Confidence(
        source_reliability=extracted.confidence,
        corroboration=0,
        extraction_certainty=extracted.confidence,
    )
    fields = [
        ExtractedField(
            attribute=f"signal/{kind}/summary",
            value=extracted.summary[:MAX_VALUE_LENGTH],
            confidence=confidence,
            extractor="llm:mock",
        )
    ]
    for index, entity in enumerate(extracted.entities[:20]):
        fields.append(
            ExtractedField(
                attribute=f"signal/{kind}/entity/{index}",
                value=entity[:MAX_VALUE_LENGTH],
                confidence=confidence,
                extractor="llm:mock",
            )
        )
    return fields


async def extract_signal(
    model: ModelPort, kind: str, content: str
) -> list[ExtractedField]:
    deterministic = deterministic_extract(kind, content)
    if deterministic:
        return deterministic
    return await llm_extract(model, kind, content)
