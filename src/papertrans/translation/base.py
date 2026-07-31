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
class TranslationResult:
    segment_id: str
    normal: str
    compact: str | None = None
    provider: str = "unknown"


class TranslationProvider(Protocol):
    name: str

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]: ...
