from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from papertrans.ingest import extract_document
from papertrans.layout import build_cjk_layout
from papertrans.qa import evaluate_roundtrip
from papertrans.render import render_translated_layout
from papertrans.translation import (
    MockTranslationProvider,
    ProtectedSegment,
    ProtectionValidation,
    ProviderExecutionError,
    ReliableTranslationProvider,
    RetryPolicy,
    protect_text_flows,
    translate_text_flows_with_protection,
)


@dataclass(frozen=True, slots=True)
class MockTranslationResult:
    output_dir: Path
    output_pdf: Path
    protected_segments_json: Path
    provider_run_json: Path
    translations_json: Path
    layout_json: Path
    report_json: Path
    report: dict[str, Any]


def _default_cache_dir(output_dir: Path, provider_name: str) -> Path:
    for candidate in (output_dir, *output_dir.parents):
        if candidate.name == ".papertrans":
            return candidate / "cache" / provider_name
    return output_dir / ".cache" / provider_name


def _write_provider_run(
    path: Path,
    status: str,
    provider_name: str,
    cache_dir: Path,
    retry_policy: RetryPolicy,
    requests_per_second: float,
    stats: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "status": status,
                "provider": provider_name,
                "cache_dir": str(cache_dir),
                "retry_policy": {
                    "max_attempts": retry_policy.max_attempts,
                    "initial_delay_seconds": retry_policy.initial_delay_seconds,
                    "multiplier": retry_policy.multiplier,
                    "maximum_delay_seconds": retry_policy.maximum_delay_seconds,
                },
                "requests_per_second": requests_per_second,
                "stats": stats or {},
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_protection_manifest(
    path: Path,
    provider_name: str,
    segments: dict[str, ProtectedSegment],
    status: str,
    validations: tuple[ProtectionValidation, ...] = (),
    stats: dict[str, Any] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "provider": provider_name,
                "status": status,
                "stats": stats
                or {
                    "segment_count": len(segments),
                    "protected_segment_count": sum(
                        bool(segment.tokens) for segment in segments.values()
                    ),
                    "token_count": sum(len(segment.tokens) for segment in segments.values()),
                },
                "segments": [segment.to_dict() for segment in segments.values()],
                "validations": [validation.to_dict() for validation in validations],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def run_mock_translation(
    source: str | Path,
    output_dir: str | Path,
    length_factor: float = 1.0,
    cache_dir: str | Path | None = None,
    max_attempts: int = 3,
    requests_per_second: float = 0.0,
) -> MockTranslationResult:
    source_path = Path(source).expanduser().resolve()
    resolved_output = Path(output_dir).expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    output_pdf = resolved_output / "output.pdf"
    temporary_pdf = resolved_output / f".{uuid4().hex}.mock.tmp.pdf"

    document = extract_document(source_path)
    provider = MockTranslationProvider(length_factor=length_factor)
    resolved_cache = (
        Path(cache_dir).expanduser().resolve()
        if cache_dir is not None
        else _default_cache_dir(resolved_output, provider.name)
    )
    retry_policy = RetryPolicy(max_attempts=max_attempts)
    reliable_provider = ReliableTranslationProvider(
        provider,
        resolved_cache,
        retry_policy=retry_policy,
        requests_per_second=requests_per_second,
    )
    provider_run_json = resolved_output / "provider-run.json"
    _write_provider_run(
        provider_run_json,
        status="prepared",
        provider_name=provider.name,
        cache_dir=resolved_cache,
        retry_policy=retry_policy,
        requests_per_second=requests_per_second,
    )
    document_json = resolved_output / "document.json"
    document_json.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    protected_segments_json = resolved_output / "protected-segments.json"
    protected_segments = protect_text_flows(document)
    _write_protection_manifest(
        protected_segments_json,
        provider.name,
        protected_segments,
        status="prepared",
    )
    try:
        translation_batch = translate_text_flows_with_protection(
            document,
            reliable_provider,
            protected_segments=protected_segments,
        )
    except ProviderExecutionError as exc:
        _write_provider_run(
            provider_run_json,
            status="failed",
            provider_name=provider.name,
            cache_dir=resolved_cache,
            retry_policy=retry_policy,
            requests_per_second=requests_per_second,
            stats=reliable_provider.stats.to_dict(),
            error={
                "segment_id": exc.segment_id,
                "attempts": exc.attempts,
                "cause_type": exc.cause_type,
            },
        )
        raise
    _write_provider_run(
        provider_run_json,
        status="completed",
        provider_name=provider.name,
        cache_dir=resolved_cache,
        retry_policy=retry_policy,
        requests_per_second=requests_per_second,
        stats=reliable_provider.stats.to_dict(),
    )
    _write_protection_manifest(
        protected_segments_json,
        provider.name,
        protected_segments,
        status="validated",
        validations=translation_batch.validations,
        stats=translation_batch.stats,
    )
    translations = translation_batch.translations
    layout = build_cjk_layout(document, translations)
    translations_json = resolved_output / "translations.json"
    translations_json.write_text(
        json.dumps(
            {
                "provider": provider.name,
                "length_factor": length_factor,
                "translations": [
                    {
                        "segment_id": result.segment_id,
                        "normal": result.normal,
                        "compact": result.compact,
                        "provider": result.provider,
                    }
                    for result in translations.values()
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    layout_json = resolved_output / "layout.json"
    layout_json.write_text(
        json.dumps(layout.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        render_stats = render_translated_layout(source_path, document, layout, temporary_pdf)
        temporary_pdf.replace(output_pdf)
    finally:
        if temporary_pdf.exists():
            temporary_pdf.unlink()

    pdf_quality = evaluate_roundtrip(source_path, output_pdf)
    gates = {
        "same_page_count": pdf_quality["same_page_count"],
        "same_page_dimensions": pdf_quality["same_page_dimensions"],
        "links_preserved": pdf_quality["links_preserved"],
        "no_layout_overflow": layout.stats["overflow_flow_count"] == 0,
        "no_new_sub_6pt_text": layout.stats["new_sub_6pt_flow_count"] == 0,
        "minimum_font_scale_at_least_0_72": layout.stats["minimum_font_scale"] >= 0.72,
        "no_translated_line_overlaps": layout.stats["translated_line_overlap_count"] == 0,
        "no_protected_region_overlaps": layout.stats["protected_region_overlap_count"] == 0,
        "protected_tokens_restored": translation_batch.stats["passed"],
        "provider_execution_completed": reliable_provider.stats.failure_count == 0,
        "rendered_lines_present": render_stats.rendered_lines > 0,
    }
    report = {
        "schema_version": "0.1",
        "source_path": str(source_path),
        "output_path": str(output_pdf),
        "mode": "mock_chinese_layout",
        "provider": provider.name,
        "length_factor": length_factor,
        "protection": translation_batch.stats,
        "provider_execution": reliable_provider.stats.to_dict(),
        "limitations": [
            "Mock Chinese is synthetic and must not be evaluated for translation quality.",
            "White fill is used when removing source text regions.",
            "The local CJK font is referenced at runtime and is not bundled with the project.",
        ],
        "layout": layout.stats,
        "render": render_stats.to_dict(),
        "pdf_quality": pdf_quality,
        "gates": gates,
        "passed": all(gates.values()),
    }
    report_json = resolved_output / "mock-translation-report.json"
    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return MockTranslationResult(
        output_dir=resolved_output,
        output_pdf=output_pdf,
        protected_segments_json=protected_segments_json,
        provider_run_json=provider_run_json,
        translations_json=translations_json,
        layout_json=layout_json,
        report_json=report_json,
        report=report,
    )
