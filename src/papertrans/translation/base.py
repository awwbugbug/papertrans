from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    segment_id: str
    text: str
    source_language: str = "en"
    target_language: str = "zh-CN"
    protected_tokens: tuple[str, ...] = ()
    context: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TranslationUsage:
    input_tokens: int
    cached_input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None
    currency: str | None = None
    pricing_snapshot: str | None = None

    def __post_init__(self) -> None:
        if min(self.input_tokens, self.cached_input_tokens, self.output_tokens) < 0:
            raise ValueError("Token usage cannot be negative")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("Cached input tokens cannot exceed input tokens")

    @property
    def uncached_input_tokens(self) -> int:
        return self.input_tokens - self.cached_input_tokens


@dataclass(frozen=True, slots=True)
class TranslationResult:
    segment_id: str
    normal: str
    compact: str | None = None
    provider: str = "unknown"
    usage: TranslationUsage | None = None


class TranslationProvider(Protocol):
    name: str

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]: ...
