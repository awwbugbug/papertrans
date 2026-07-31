from __future__ import annotations

from pathlib import Path

from papertrans.translation import MockTranslationProvider
from papertrans.translation_job import TranslationJobResult, run_translation_job

MockTranslationResult = TranslationJobResult


def run_mock_translation(
    source: str | Path,
    output_dir: str | Path,
    length_factor: float = 1.0,
    cache_dir: str | Path | None = None,
    max_attempts: int = 3,
    requests_per_second: float = 0.0,
) -> MockTranslationResult:
    provider = MockTranslationProvider(length_factor=length_factor)
    return run_translation_job(
        source,
        output_dir,
        provider,
        cache_dir=cache_dir,
        max_attempts=max_attempts,
        requests_per_second=requests_per_second,
    )
