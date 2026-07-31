from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from papertrans.domain import Document
from papertrans.translation.base import (
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)
from papertrans.translation.protection import (
    ProtectedSegment,
    ProtectedTokenError,
    ProtectionValidation,
    protect_text,
    restore_text,
)


@dataclass(frozen=True, slots=True)
class ProtectedTranslationBatch:
    translations: dict[str, TranslationResult]
    segments: dict[str, ProtectedSegment]
    validations: tuple[ProtectionValidation, ...]

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "segment_count": len(self.segments),
            "protected_segment_count": sum(
                bool(segment.tokens) for segment in self.segments.values()
            ),
            "token_count": sum(len(segment.tokens) for segment in self.segments.values()),
            "restored_token_count": sum(item.restored_count for item in self.validations),
            "missing_token_count": sum(len(item.missing) for item in self.validations),
            "duplicated_token_count": sum(len(item.duplicated) for item in self.validations),
            "unknown_token_count": sum(len(item.unknown) for item in self.validations),
            "passed": all(item.passed for item in self.validations),
        }


def translate_text_flows(
    document: Document,
    provider: TranslationProvider,
    source_language: str = "en",
    target_language: str = "zh-CN",
) -> dict[str, TranslationResult]:
    return translate_text_flows_with_protection(
        document,
        provider,
        source_language=source_language,
        target_language=target_language,
    ).translations


def protect_text_flows(document: Document) -> dict[str, ProtectedSegment]:
    return {
        flow.id: protect_text(flow.id, flow.source_text)
        for flow in document.text_flows
        if flow.translatable and flow.source_text
    }


def translate_text_flows_with_protection(
    document: Document,
    provider: TranslationProvider,
    source_language: str = "en",
    target_language: str = "zh-CN",
    protected_segments: dict[str, ProtectedSegment] | None = None,
) -> ProtectedTranslationBatch:
    flow_by_id = {flow.id: flow for flow in document.text_flows}
    segments = protected_segments or protect_text_flows(document)
    requests = [
        TranslationRequest(
            segment_id=segment.segment_id,
            text=segment.protected_text,
            source_language=source_language,
            target_language=target_language,
            protected_tokens=tuple(token.placeholder for token in segment.tokens),
            context={
                "region_type": flow_by_id[segment.segment_id].type.value,
            },
        )
        for segment in segments.values()
    ]
    results = provider.translate(requests)
    by_id = {result.segment_id: result for result in results}
    missing = [request.segment_id for request in requests if request.segment_id not in by_id]
    if missing:
        raise RuntimeError(f"Translation provider omitted {len(missing)} segments")

    restored_results: dict[str, TranslationResult] = {}
    validations: list[ProtectionValidation] = []
    for request in requests:
        result = by_id[request.segment_id]
        segment = segments[request.segment_id]
        normal, normal_validation = restore_text(result.normal, segment, "normal")
        validations.append(normal_validation)
        if not normal_validation.passed:
            raise ProtectedTokenError(normal_validation)
        compact = None
        if result.compact is not None:
            compact, compact_validation = restore_text(result.compact, segment, "compact")
            validations.append(compact_validation)
            if not compact_validation.passed:
                raise ProtectedTokenError(compact_validation)
        restored_results[result.segment_id] = TranslationResult(
            segment_id=result.segment_id,
            normal=normal,
            compact=compact,
            provider=result.provider,
            usage=result.usage,
        )
    return ProtectedTranslationBatch(
        translations=restored_results,
        segments=segments,
        validations=tuple(validations),
    )
