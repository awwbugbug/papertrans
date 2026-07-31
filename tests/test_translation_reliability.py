from pathlib import Path

import pytest

from papertrans.translation import (
    ProviderExecutionError,
    ReliableTranslationProvider,
    RetryPolicy,
    TranslationRequest,
    TranslationResult,
)


class _CountingProvider:
    name = "counting"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        request = requests[0]
        self.calls.append(request.segment_id)
        return [
            TranslationResult(
                segment_id=request.segment_id,
                normal=f"译文:{request.text}",
                compact=f"短:{request.text}",
                provider=self.name,
            )
        ]


def _requests() -> list[TranslationRequest]:
    return [
        TranslationRequest(segment_id="s1", text="first"),
        TranslationRequest(segment_id="s2", text="second"),
    ]


def test_disk_cache_reuses_results_without_provider_calls(tmp_path: Path) -> None:
    first_provider = _CountingProvider()
    first = ReliableTranslationProvider(first_provider, tmp_path / "cache")

    initial_results = first.translate(_requests())

    assert first_provider.calls == ["s1", "s2"]
    assert first.stats.cache_misses == 2
    assert first.stats.cache_writes == 2

    second_provider = _CountingProvider()
    second = ReliableTranslationProvider(second_provider, tmp_path / "cache")
    cached_results = second.translate(_requests())

    assert second_provider.calls == []
    assert second.stats.cache_hits == 2
    assert [result.normal for result in cached_results] == [
        result.normal for result in initial_results
    ]
    assert [result.segment_id for result in cached_results] == ["s1", "s2"]


class _ConfiguredProvider(_CountingProvider):
    name = "configured"

    def __init__(self, version: str) -> None:
        super().__init__()
        self.cache_identity = {"provider": self.name, "version": version}


def test_provider_configuration_fingerprint_separates_cache_entries(tmp_path: Path) -> None:
    first_provider = _ConfiguredProvider("v1")
    ReliableTranslationProvider(first_provider, tmp_path / "cache").translate(_requests())
    second_provider = _ConfiguredProvider("v2")
    second = ReliableTranslationProvider(second_provider, tmp_path / "cache")

    second.translate(_requests())

    assert second.stats.cache_hits == 0
    assert second_provider.calls == ["s1", "s2"]


class _FlakyProvider(_CountingProvider):
    name = "flaky"

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        self.calls.append(requests[0].segment_id)
        if self.failures:
            self.failures -= 1
            raise TimeoutError("temporary failure")
        return [
            TranslationResult(
                segment_id=requests[0].segment_id,
                normal="成功",
                provider=self.name,
            )
        ]


def test_retry_uses_exponential_backoff(tmp_path: Path) -> None:
    provider = _FlakyProvider(failures=2)
    sleeps: list[float] = []
    reliable = ReliableTranslationProvider(
        provider,
        tmp_path / "cache",
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.1,
            multiplier=2,
            maximum_delay_seconds=1,
        ),
        sleep=sleeps.append,
    )

    results = reliable.translate([TranslationRequest(segment_id="s1", text="source")])

    assert results[0].normal == "成功"
    assert provider.calls == ["s1", "s1", "s1"]
    assert sleeps == [0.1, 0.2]
    assert reliable.stats.retry_count == 2
    assert reliable.stats.failure_count == 0


class _PartialFailureProvider(_CountingProvider):
    name = "recoverable"

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        request = requests[0]
        self.calls.append(request.segment_id)
        if request.segment_id == "s2":
            raise ConnectionError("offline")
        return [
            TranslationResult(
                segment_id=request.segment_id,
                normal=f"译文:{request.text}",
                provider=self.name,
            )
        ]


class _RecoveredProvider(_CountingProvider):
    name = "recoverable"


def test_successful_segments_resume_from_cache_after_partial_failure(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    failing = _PartialFailureProvider()
    first = ReliableTranslationProvider(
        failing,
        cache_dir,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    requests = [*_requests(), TranslationRequest(segment_id="s3", text="third")]

    with pytest.raises(ProviderExecutionError) as exc_info:
        first.translate(requests)

    assert exc_info.value.segment_id == "s2"
    assert failing.calls == ["s1", "s2"]
    recovered_provider = _RecoveredProvider()
    recovered = ReliableTranslationProvider(recovered_provider, cache_dir)
    results = recovered.translate(requests)
    assert [result.segment_id for result in results] == ["s1", "s2", "s3"]
    assert recovered.stats.cache_hits == 1
    assert recovered_provider.calls == ["s2", "s3"]


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_rate_limit_spaces_provider_calls(tmp_path: Path) -> None:
    fake = _FakeClock()
    provider = _CountingProvider()
    reliable = ReliableTranslationProvider(
        provider,
        tmp_path / "cache",
        requests_per_second=2,
        sleep=fake.sleep,
        clock=fake.clock,
    )
    requests = [*_requests(), TranslationRequest(segment_id="s3", text="third")]

    reliable.translate(requests)

    assert fake.sleeps == [0.5, 0.5]
    assert reliable.stats.rate_limit_sleep_seconds == 1.0
