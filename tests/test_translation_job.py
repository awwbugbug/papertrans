import json
from pathlib import Path

import pymupdf
import pytest

from papertrans.translation import (
    NonRetryableProviderError,
    ProviderExecutionError,
    TranslationRequest,
    TranslationResult,
)
from papertrans.translation_job import run_translation_job


class DeterministicProvider:
    name = "deterministic"
    cache_identity = {
        "provider": "deterministic",
        "version": "v1",
        "accounting": {"input_tokens": 0, "max_output_tokens": 1024},
    }

    def __init__(self) -> None:
        self.calls: list[str] = []

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        request = requests[0]
        self.calls.append(request.segment_id)
        suffix = "".join(request.protected_tokens)
        return [
            TranslationResult(
                segment_id=request.segment_id,
                normal=f"这是正常中文译文{suffix}",
                compact=f"紧凑译文{suffix}",
                provider=self.name,
            )
        ]


def _create_fixture(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_textbox(
        pymupdf.Rect(40, 80, 380, 260),
        "A paper paragraph cites https://example.org and finishes in 10 ms.",
        fontsize=9,
    )
    document.save(path)
    document.close()


def test_generic_job_writes_provider_neutral_artifacts_and_resumes(tmp_path: Path) -> None:
    source = tmp_path / "fixture.pdf"
    _create_fixture(source)
    cache_dir = tmp_path / "cache"

    first_provider = DeterministicProvider()
    first = run_translation_job(
        source,
        tmp_path / "first",
        first_provider,
        cache_dir=cache_dir,
    )
    assert first.output_pdf.is_file()
    assert first.report_json.name == "translation-report.json"
    assert first.report["provider"] == "deterministic"
    assert first.report["mode"] == "translated_pdf"
    assert any("deterministic" in item for item in first.report["limitations"])
    assert first.report["gates"]["provider_execution_completed"] is True
    assert first_provider.calls
    provider_run = json.loads(first.provider_run_json.read_text(encoding="utf-8"))
    assert provider_run["status"] == "completed"
    assert provider_run["provider_configuration"] == DeterministicProvider.cache_identity

    second_provider = DeterministicProvider()
    second = run_translation_job(
        source,
        tmp_path / "second",
        second_provider,
        cache_dir=cache_dir,
    )
    assert second_provider.calls == []
    assert second.report["provider_execution"]["cache_hits"] > 0
    assert second.report["provider_execution"]["usage"]["input_tokens"] == 0


@pytest.mark.parametrize(
    "secret_field",
    ["api_key", "Authorization", "client_secret", "credentials"],
)
def test_job_rejects_nested_secret_bearing_cache_identity_before_writing(
    tmp_path: Path,
    secret_field: str,
) -> None:
    provider = DeterministicProvider()
    provider.cache_identity = {
        "provider": provider.name,
        "nested": [{secret_field: "sentinel-secret-value"}],
    }
    output_dir = tmp_path / "output"

    with pytest.raises(ValueError, match="secret-bearing"):
        run_translation_job(tmp_path / "missing.pdf", output_dir, provider)

    assert not output_dir.exists()


def test_failed_job_writes_only_sanitized_provider_error_summary(tmp_path: Path) -> None:
    class FailingProvider(DeterministicProvider):
        name = "failing"
        cache_identity = {"provider": "failing", "version": "v1"}

        def translate(
            self,
            requests: list[TranslationRequest],
        ) -> list[TranslationResult]:
            raise NonRetryableProviderError(
                error_type="provider_http_error",
                http_status=401,
            )

    source = tmp_path / "fixture.pdf"
    output_dir = tmp_path / "failed"
    _create_fixture(source)

    with pytest.raises(ProviderExecutionError):
        run_translation_job(source, output_dir, FailingProvider(), max_attempts=1)

    provider_run = json.loads(
        (output_dir / "provider-run.json").read_text(encoding="utf-8")
    )
    assert provider_run["status"] == "failed"
    assert provider_run["error"] == {
        "segment_id": "flow-p1-text-0",
        "attempts": 1,
        "error_type": "provider_http_error",
        "http_status": 401,
    }


def test_failed_job_drops_untrusted_http_status_text(tmp_path: Path) -> None:
    sentinel = "sentinel-secret-status"

    class UnsafeFailureProvider(DeterministicProvider):
        name = "unsafe-failure"
        cache_identity = {"provider": "unsafe-failure", "version": "v1"}

        def translate(
            self,
            requests: list[TranslationRequest],
        ) -> list[TranslationResult]:
            raise NonRetryableProviderError(
                error_type=f"unsafe:{sentinel}",
                http_status=sentinel,  # type: ignore[arg-type]
            )

    source = tmp_path / "fixture.pdf"
    output_dir = tmp_path / "failed"
    _create_fixture(source)

    with pytest.raises(ProviderExecutionError):
        run_translation_job(source, output_dir, UnsafeFailureProvider(), max_attempts=1)

    provider_run = json.loads(
        (output_dir / "provider-run.json").read_text(encoding="utf-8")
    )
    assert provider_run["error"] == {
        "segment_id": "flow-p1-text-0",
        "attempts": 1,
        "error_type": "provider_error",
        "http_status": None,
    }
    assert sentinel not in json.dumps(provider_run)
