from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from papertrans.ingest import (
    OCRPreflightError,
    OCRRuntimeConfig,
    annotate_document_with_ocr_plan,
    prepare_document,
)
from papertrans.layout import build_cjk_layout, validate_layout
from papertrans.qa import evaluate_roundtrip
from papertrans.render import render_translated_layout
from papertrans.translation import (
    ProtectedSegment,
    ProtectedTokenError,
    ProtectionValidation,
    ProviderExecutionError,
    ReliableTranslationProvider,
    RetryPolicy,
    TranslationProvider,
    protect_text_flows,
    translate_text_flows_with_protection,
)

_SECRET_FIELD_MARKERS = {
    "accesstoken",
    "apikey",
    "authtoken",
    "authorization",
    "bearertoken",
    "credential",
    "passphrase",
    "password",
    "privatekey",
    "refreshtoken",
    "secret",
}
_SAFE_TOKEN_FIELD_NAMES = {
    "cachedinputtokens",
    "cachedtokens",
    "completiontokens",
    "contextwindowtokens",
    "inputtokens",
    "maxinputtokens",
    "maxoutputtokens",
    "maxtokens",
    "outputtokens",
    "promptcachehittokens",
    "promptcachemisstokens",
    "prompttokens",
    "protectedtokencount",
    "tokencount",
    "tokenizer",
    "tokenizerversion",
    "totaltokens",
    "uncachedinputtokens",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"Bearer\s+\S{8,}", re.IGNORECASE),
    re.compile(r"sk-[a-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"api[-_]?key(?:[-_:][a-z0-9_-]+)+", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class TranslationJobResult:
    output_dir: Path
    output_pdf: Path
    ocr_plan_json: Path
    protected_segments_json: Path
    provider_run_json: Path
    translations_json: Path
    layout_json: Path
    report_json: Path
    report: dict[str, Any]
    ocr_run_json: Path | None = None


def _default_cache_dir(output_dir: Path, provider_name: str) -> Path:
    for candidate in (output_dir, *output_dir.parents):
        if candidate.name == ".papertrans":
            return candidate / "cache" / provider_name
    return output_dir / ".cache" / provider_name


def _provider_configuration(provider: TranslationProvider) -> dict[str, Any]:
    identity = getattr(provider, "cache_identity", {"provider": provider.name})
    if not isinstance(identity, dict):
        raise ValueError("Provider cache_identity must be a dictionary")
    try:
        configuration = json.loads(json.dumps(identity, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("Provider cache_identity must be JSON-serializable") from exc
    if not isinstance(configuration, dict):
        raise ValueError("Provider cache_identity must be a dictionary")
    _reject_secret_bearing_fields(configuration)
    return configuration


def _reject_secret_bearing_fields(value: Any) -> None:
    if isinstance(value, dict):
        for field_name, nested in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", field_name.lower())
            has_secret_marker = any(
                marker in normalized for marker in _SECRET_FIELD_MARKERS
            )
            has_disallowed_token = (
                "token" in normalized and normalized not in _SAFE_TOKEN_FIELD_NAMES
            )
            if has_secret_marker or has_disallowed_token:
                raise ValueError(
                    "Provider cache_identity contains a secret-bearing field name"
                )
            _reject_secret_bearing_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_secret_bearing_fields(nested)
    elif isinstance(value, str) and any(
        pattern.fullmatch(value.strip()) for pattern in _SECRET_VALUE_PATTERNS
    ):
        raise ValueError("Provider cache_identity contains a secret-bearing value")


def _sanitized_http_status(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
        return value
    return None


def _sanitized_segment_id(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", value):
        return value
    return None


def _sanitized_attempts(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _execution_error_summary(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ProviderExecutionError):
        return {
            "segment_id": _sanitized_segment_id(exc.segment_id),
            "attempts": _sanitized_attempts(exc.attempts),
            "error_type": exc.error_type,
            "http_status": _sanitized_http_status(exc.http_status),
        }
    if isinstance(exc, ProtectedTokenError):
        return {
            "segment_id": _sanitized_segment_id(exc.validation.segment_id),
            "attempts": None,
            "error_type": "protected_token_error",
            "http_status": None,
        }
    return {
        "segment_id": None,
        "attempts": None,
        "error_type": "translation_execution_error",
        "http_status": None,
    }


def _write_provider_run(
    path: Path,
    status: str,
    provider_name: str,
    provider_configuration: dict[str, Any],
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
                "provider_configuration": provider_configuration,
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


def _report_limitations(provider_name: str) -> list[str]:
    if provider_name == "mock":
        provider_limitation = (
            "Mock Chinese is synthetic and must not be evaluated for translation quality."
        )
    else:
        provider_limitation = (
            f"Source text is transmitted to the selected external provider: {provider_name}."
        )
    return [
        provider_limitation,
        "White fill is used when removing source text regions.",
        "The local CJK font is referenced at runtime and is not bundled with the project.",
    ]


def run_translation_job(
    source: str | Path,
    output_dir: str | Path,
    provider: TranslationProvider,
    *,
    cache_dir: str | Path | None = None,
    max_attempts: int = 3,
    requests_per_second: float = 0.0,
    glossary: Mapping[str, str] | None = None,
    ocr_config: OCRRuntimeConfig | None = None,
) -> TranslationJobResult:
    source_path = Path(source).expanduser().resolve()
    resolved_output = Path(output_dir).expanduser().resolve()
    provider_configuration = _provider_configuration(provider)
    resolved_output.mkdir(parents=True, exist_ok=True)
    output_pdf = resolved_output / "output.pdf"
    temporary_pdf = resolved_output / f".{uuid4().hex}.translation.tmp.pdf"

    preparation = prepare_document(source_path, ocr_config)
    document = preparation.document
    ocr_plan = preparation.plan
    annotate_document_with_ocr_plan(document, ocr_plan)
    document_json = resolved_output / "document.json"
    document_json.write_text(
        json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ocr_plan_json = resolved_output / "ocr-plan.json"
    ocr_plan_json.write_text(
        json.dumps(ocr_plan.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ocr_run_json = resolved_output / "ocr-run.json"
    ocr_run_json.write_text(
        json.dumps(preparation.run.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if ocr_plan.blocking_page_numbers:
        raise OCRPreflightError(ocr_plan.blocking_page_numbers, ocr_plan_json)

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
        provider_configuration=provider_configuration,
        cache_dir=resolved_cache,
        retry_policy=retry_policy,
        requests_per_second=requests_per_second,
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
            glossary=glossary,
        )
    except Exception as exc:
        _write_provider_run(
            provider_run_json,
            status="failed",
            provider_name=provider.name,
            provider_configuration=provider_configuration,
            cache_dir=resolved_cache,
            retry_policy=retry_policy,
            requests_per_second=requests_per_second,
            stats=reliable_provider.stats.to_dict(),
            error=_execution_error_summary(exc),
        )
        if isinstance(exc, (ProviderExecutionError, ProtectedTokenError)):
            raise
        raise RuntimeError("Translation execution failed") from None
    _write_provider_run(
        provider_run_json,
        status="completed",
        provider_name=provider.name,
        provider_configuration=provider_configuration,
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

    layout_safety = validate_layout(
        document,
        layout,
        expected_flow_ids=translations,
    )
    gates = {
        "complete_layout_selection": (
            layout_safety.missing_flow_count == 0
            and layout_safety.duplicate_flow_count == 0
            and layout_safety.unexpected_flow_count == 0
        ),
        "layout_geometry_valid": (
            layout_safety.region_binding_count == 0
            and layout_safety.page_bounds_count == 0
        ),
        "no_layout_overflow": layout_safety.overflow_flow_count == 0,
        "no_new_sub_6pt_text": layout.stats["new_sub_6pt_flow_count"] == 0,
        "minimum_font_scale_at_least_0_72": layout.stats["minimum_font_scale"] >= 0.72,
        "no_translated_line_overlaps": layout_safety.translated_overlap_count == 0,
        "no_protected_region_overlaps": layout_safety.protected_overlap_count == 0,
        "protected_tokens_restored": translation_batch.stats["passed"],
        "provider_execution_completed": reliable_provider.stats.failure_count == 0,
    }
    render_payload: dict[str, Any]
    pdf_quality: dict[str, Any]
    output_replaced = False
    if layout_safety.passed:
        try:
            render_stats = render_translated_layout(source_path, document, layout, temporary_pdf)
            pdf_quality = evaluate_roundtrip(source_path, temporary_pdf)
            gates.update(
                {
                    "same_page_count": pdf_quality["same_page_count"],
                    "same_page_dimensions": pdf_quality["same_page_dimensions"],
                    "links_preserved": pdf_quality["links_preserved"],
                    "rendered_lines_present": render_stats.rendered_lines > 0,
                }
            )
            render_payload = render_stats.to_dict()
            if all(gates.values()):
                temporary_pdf.replace(output_pdf)
                output_replaced = True
        finally:
            if temporary_pdf.exists():
                temporary_pdf.unlink()
    else:
        gates.update(
            {
                "same_page_count": False,
                "same_page_dimensions": False,
                "links_preserved": False,
                "rendered_lines_present": False,
            }
        )
        render_payload = {"skipped": True, "reason": "layout_safety_review"}
        pdf_quality = {"skipped": True, "reason": "layout_safety_review"}

    passed = all(gates.values())
    if passed:
        review_reasons: list[str] = []
    elif not layout_safety.passed:
        review_reasons = list(layout_safety.violations)
    else:
        review_reasons = [gate for gate, value in gates.items() if not value]
    report = {
        "schema_version": "0.1",
        "status": "pass" if passed else "review",
        "source_path": str(source_path),
        "output_path": str(output_pdf),
        "output_replaced": output_replaced,
        "review_reasons": review_reasons,
        "mode": "translated_pdf",
        "provider": provider.name,
        "provider_configuration": provider_configuration,
        "ocr_preflight": ocr_plan.to_dict(),
        "protection": translation_batch.stats,
        "translation_context": translation_batch.context_stats.to_dict(),
        "provider_execution": reliable_provider.stats.to_dict(),
        "limitations": _report_limitations(provider.name),
        "layout": layout.stats,
        "layout_safety": layout_safety.to_dict(),
        "render": render_payload,
        "pdf_quality": pdf_quality,
        "gates": gates,
        "passed": passed,
    }
    report_json = resolved_output / "translation-report.json"
    report_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return TranslationJobResult(
        output_dir=resolved_output,
        output_pdf=output_pdf,
        ocr_plan_json=ocr_plan_json,
        ocr_run_json=ocr_run_json,
        protected_segments_json=protected_segments_json,
        provider_run_json=provider_run_json,
        translations_json=translations_json,
        layout_json=layout_json,
        report_json=report_json,
        report=report,
    )
