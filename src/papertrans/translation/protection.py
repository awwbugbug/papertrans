from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

_PLACEHOLDER = re.compile(r"⟦PT\d{4}⟧")
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "url",
        re.compile(r"(?:https?://|www\.)[^\s<>\[\]{}]+", re.IGNORECASE),
    ),
    (
        "doi",
        re.compile(r"\b(?:doi:\s*)?10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE),
    ),
    ("latex", re.compile(r"\$[^$\n]{1,200}\$")),
    (
        "citation",
        re.compile(r"\[(?:\s*\d+[a-z]?\s*(?:[-,;]\s*\d+[a-z]?\s*)*)\]", re.IGNORECASE),
    ),
    (
        "unit",
        re.compile(
            r"(?<!\w)\d+(?:\.\d+)?(?:\s*[×x]\s*\d+(?:\.\d+)?)?\s*"
            r"(?:%|°C|°F|ms|μs|ns|s|Hz|kHz|MHz|GHz|B|KB|MB|GB|TB|px|mm|cm|m|km)(?!\w)",
            re.IGNORECASE,
        ),
    ),
    (
        "variable",
        re.compile(
            r"(?<!\w)(?:[A-Za-z]{1,3}(?:[_^](?:\{[^}\n]{1,20}\}|[A-Za-z0-9]+))+|"
            r"[α-ωΑ-Ω](?:[_^](?:\{[^}\n]{1,20}\}|[A-Za-z0-9]+))?)(?!\w)"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ProtectedToken:
    placeholder: str
    value: str
    kind: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "placeholder": self.placeholder,
            "value": self.value,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True, slots=True)
class ProtectedSegment:
    segment_id: str
    source_text: str
    protected_text: str
    tokens: tuple[ProtectedToken, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "source_sha256": hashlib.sha256(self.source_text.encode("utf-8")).hexdigest(),
            "source_length": len(self.source_text),
            "protected_text": self.protected_text,
            "tokens": [token.to_dict() for token in self.tokens],
        }


@dataclass(frozen=True, slots=True)
class ProtectionValidation:
    segment_id: str
    variant: str
    expected_count: int
    restored_count: int
    missing: tuple[str, ...]
    duplicated: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing and not self.duplicated and not self.unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "variant": self.variant,
            "expected_count": self.expected_count,
            "restored_count": self.restored_count,
            "missing": list(self.missing),
            "duplicated": list(self.duplicated),
            "unknown": list(self.unknown),
            "passed": self.passed,
        }


class ProtectedTokenError(RuntimeError):
    def __init__(self, validation: ProtectionValidation) -> None:
        self.validation = validation
        super().__init__(
            f"Protected token validation failed for {validation.segment_id} "
            f"({validation.variant}): missing={len(validation.missing)}, "
            f"duplicated={len(validation.duplicated)}, unknown={len(validation.unknown)}"
        )


def protect_text(segment_id: str, text: str) -> ProtectedSegment:
    candidates: list[tuple[int, int, int, str]] = []
    for priority, (kind, pattern) in enumerate(_PATTERNS):
        for match in pattern.finditer(text):
            end = match.end()
            if kind in {"url", "doi"}:
                end -= len(text[match.start() : end]) - len(
                    text[match.start() : end].rstrip(".,;:")
                )
            if end > match.start():
                candidates.append((match.start(), end, priority, kind))

    selected: list[tuple[int, int, str]] = []
    for start, end, _priority, kind in sorted(
        candidates,
        key=lambda item: (item[0], item[2], -(item[1] - item[0])),
    ):
        if any(
            start < existing_end and end > existing_start
            for existing_start, existing_end, _ in selected
        ):
            continue
        selected.append((start, end, kind))
    selected.sort(key=lambda item: item[0])

    tokens: list[ProtectedToken] = []
    pieces: list[str] = []
    cursor = 0
    for index, (start, end, kind) in enumerate(selected, start=1):
        placeholder = f"⟦PT{index:04d}⟧"
        pieces.extend((text[cursor:start], placeholder))
        tokens.append(
            ProtectedToken(
                placeholder=placeholder,
                value=text[start:end],
                kind=kind,
                start=start,
                end=end,
            )
        )
        cursor = end
    pieces.append(text[cursor:])
    return ProtectedSegment(
        segment_id=segment_id,
        source_text=text,
        protected_text="".join(pieces),
        tokens=tuple(tokens),
    )


def restore_text(
    text: str,
    segment: ProtectedSegment,
    variant: str,
) -> tuple[str, ProtectionValidation]:
    expected = {token.placeholder: token for token in segment.tokens}
    counts = {placeholder: text.count(placeholder) for placeholder in expected}
    missing = tuple(placeholder for placeholder, count in counts.items() if count == 0)
    duplicated = tuple(placeholder for placeholder, count in counts.items() if count > 1)
    unknown = tuple(sorted(set(_PLACEHOLDER.findall(text)) - set(expected)))
    restored = text
    for placeholder, token in expected.items():
        restored = restored.replace(placeholder, token.value)
    validation = ProtectionValidation(
        segment_id=segment.segment_id,
        variant=variant,
        expected_count=len(expected),
        restored_count=sum(count == 1 for count in counts.values()),
        missing=missing,
        duplicated=duplicated,
        unknown=unknown,
    )
    return restored, validation
