from typing import Annotated, Any, Mapping, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

T = TypeVar("T", bound=BaseModel)


class ExtractedSignal(BaseModel):
    """Strict output contract for the tool-less extractor."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(max_length=64)
    summary: str = Field(max_length=500)
    entities: list[Annotated[str, StringConstraints(max_length=200)]] = Field(
        default_factory=list,
        max_length=20,
    )
    confidence: float = Field(default=0.5, ge=0, le=1)


class ModelPort(Protocol):
    """Thin boundary. Core logic never imports a vendor SDK directly."""

    async def extract(self, raw: str, schema: type[T]) -> T: ...

    async def draft(self, prompt: str, context: Mapping[str, Any]) -> str: ...


class MockModelAdapter:
    """Deterministic, network-free adapter for local development."""

    async def extract(self, raw: str, schema: type[T]) -> T:
        if schema is ExtractedSignal:
            return schema(  # type: ignore[return-value]
                kind="unknown",
                summary=f"Mock extraction of {len(raw)} chars",
                entities=[],
                confidence=0.5,
            )
        raise ValueError(f"MockModelAdapter has no extraction for {schema.__name__}")

    async def draft(self, prompt: str, context: Mapping[str, Any]) -> str:
        return f"[MOCK DRAFT] {prompt.strip()[:120]}"


def get_model_port(provider: str = "mock") -> ModelPort:
    if provider == "mock":
        return MockModelAdapter()
    raise ValueError(f"Unsupported model provider: {provider}")
