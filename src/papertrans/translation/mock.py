from __future__ import annotations

import re

from papertrans.translation.base import TranslationRequest, TranslationResult


class MockTranslationProvider:
    """Deterministic CJK-shaped output for layout testing without API calls."""

    name = "mock"
    _sample = "这是用于论文版式压力测试的模拟中文内容，主要验证段落换行、字号调整与页面布局。"

    def __init__(self, length_factor: float = 1.0) -> None:
        if length_factor <= 0:
            raise ValueError("length_factor must be positive")
        self.length_factor = length_factor

    @property
    def cache_identity(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "implementation": "deterministic_cjk_v2",
            "length_factor": self.length_factor,
        }

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        results: list[TranslationResult] = []
        for request in requests:
            plain_source = request.text
            for token in request.protected_tokens:
                plain_source = plain_source.replace(token, "")
            source_length = max(1, len(plain_source.replace(" ", "")))
            target_length = max(1, round(source_length * 0.55 * self.length_factor))
            normal = self._generate_with_tokens(request, target_length)
            compact = self._generate_with_tokens(request, max(1, round(target_length * 0.82)))
            results.append(
                TranslationResult(
                    segment_id=request.segment_id,
                    normal=normal,
                    compact=compact,
                    provider=self.name,
                )
            )
        return results

    @classmethod
    def _generate_with_tokens(cls, request: TranslationRequest, target_length: int) -> str:
        generated = cls._generate_text(target_length)
        if not request.protected_tokens:
            return generated
        token_pattern = re.compile(
            "(" + "|".join(re.escape(token) for token in request.protected_tokens) + ")"
        )
        parts = token_pattern.split(request.text)
        plain_total = max(
            1,
            sum(
                len(part.replace(" ", ""))
                for part in parts
                if part not in request.protected_tokens
            ),
        )
        output: list[str] = []
        generated_cursor = 0
        plain_seen = 0
        for part in parts:
            if part in request.protected_tokens:
                target_cursor = round(len(generated) * plain_seen / plain_total)
                output.append(generated[generated_cursor:target_cursor])
                output.append(part)
                generated_cursor = target_cursor
            else:
                plain_seen += len(part.replace(" ", ""))
        output.append(generated[generated_cursor:])
        return "".join(output)

    @classmethod
    def _generate_text(cls, target_length: int) -> str:
        repeats = (target_length // len(cls._sample)) + 1
        text = (cls._sample * repeats)[:target_length]
        if target_length >= 4 and text[-1] not in "。！？":
            text = f"{text[:-1]}。"
        return text
