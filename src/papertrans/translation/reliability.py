from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from papertrans.translation.base import (
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    multiplier: float = 2.0
    maximum_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds cannot be negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")
        if self.maximum_delay_seconds < 0:
            raise ValueError("maximum_delay_seconds cannot be negative")


@dataclass(slots=True)
class ProviderRunStats:
    request_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_writes: int = 0
    cache_errors: int = 0
    provider_calls: int = 0
    retry_count: int = 0
    failure_count: int = 0
    rate_limit_sleep_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_writes": self.cache_writes,
            "cache_errors": self.cache_errors,
            "provider_calls": self.provider_calls,
            "retry_count": self.retry_count,
            "failure_count": self.failure_count,
            "rate_limit_sleep_seconds": round(self.rate_limit_sleep_seconds, 3),
            "completed": self.failure_count == 0,
        }


class NonRetryableProviderError(RuntimeError):
    """A provider error that should fail immediately, such as invalid credentials."""


class ProviderExecutionError(RuntimeError):
    def __init__(self, segment_id: str, attempts: int, cause: Exception) -> None:
        self.segment_id = segment_id
        self.attempts = attempts
        self.cause_type = type(cause).__name__
        super().__init__(
            f"Translation provider failed for segment {segment_id} after {attempts} attempt(s) "
            f"with {self.cause_type}"
        )


class ReliableTranslationProvider:
    """Add deterministic cache, retry, rate limiting, and resumability to any provider."""

    def __init__(
        self,
        provider: TranslationProvider,
        cache_dir: str | Path,
        retry_policy: RetryPolicy | None = None,
        requests_per_second: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if requests_per_second < 0:
            raise ValueError("requests_per_second cannot be negative")
        self.provider = provider
        self.name = provider.name
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.retry_policy = retry_policy or RetryPolicy()
        self.requests_per_second = requests_per_second
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self.stats = ProviderRunStats()

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        self.stats = ProviderRunStats(request_count=len(requests))
        results: list[TranslationResult] = []
        for request in requests:
            cache_key = self._cache_key(request)
            cached = self._read_cache(cache_key, request.segment_id)
            if cached is not None:
                self.stats.cache_hits += 1
                results.append(cached)
                continue
            self.stats.cache_misses += 1
            result = self._translate_one(request)
            self._write_cache(cache_key, result)
            results.append(result)
        return results

    def _translate_one(self, request: TranslationRequest) -> TranslationResult:
        delay = self.retry_policy.initial_delay_seconds
        last_error: Exception | None = None
        attempts = 0
        for attempts in range(1, self.retry_policy.max_attempts + 1):
            try:
                self._apply_rate_limit()
                self.stats.provider_calls += 1
                results = self.provider.translate([request])
                if len(results) != 1 or results[0].segment_id != request.segment_id:
                    raise RuntimeError("Provider returned an invalid single-segment response")
                return results[0]
            except NonRetryableProviderError as exc:
                last_error = exc
                break
            except Exception as exc:
                last_error = exc
                if attempts >= self.retry_policy.max_attempts:
                    break
                self.stats.retry_count += 1
                if delay > 0:
                    self._sleep(delay)
                delay = min(
                    delay * self.retry_policy.multiplier,
                    self.retry_policy.maximum_delay_seconds,
                )
        self.stats.failure_count += 1
        assert last_error is not None
        raise ProviderExecutionError(request.segment_id, attempts, last_error) from last_error

    def _apply_rate_limit(self) -> None:
        if self.requests_per_second <= 0:
            return
        now = self._clock()
        if self._last_request_at is not None:
            minimum_interval = 1.0 / self.requests_per_second
            wait_seconds = self._last_request_at + minimum_interval - now
            if wait_seconds > 0:
                self._sleep(wait_seconds)
                self.stats.rate_limit_sleep_seconds += wait_seconds
                now = self._clock()
        self._last_request_at = now

    def _cache_key(self, request: TranslationRequest) -> str:
        payload = {
            "schema_version": "0.1",
            "provider_identity": getattr(
                self.provider,
                "cache_identity",
                {"provider": self.provider.name},
            ),
            "source_language": request.source_language,
            "target_language": request.target_language,
            "text": request.text,
            "protected_tokens": list(request.protected_tokens),
            "context": request.context,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / cache_key[:2] / f"{cache_key}.json"

    def _read_cache(self, cache_key: str, segment_id: str) -> TranslationResult | None:
        path = self._cache_path(cache_key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != "0.1" or payload.get("provider") != self.name:
                raise ValueError("Cache metadata does not match the provider")
            normal = payload["normal"]
            compact = payload.get("compact")
            if not isinstance(normal, str) or compact is not None and not isinstance(compact, str):
                raise ValueError("Cache translation fields are invalid")
            return TranslationResult(
                segment_id=segment_id,
                normal=normal,
                compact=compact,
                provider=payload["provider"],
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.stats.cache_errors += 1
            return None

    def _write_cache(self, cache_key: str, result: TranslationResult) -> None:
        path = self._cache_path(cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        payload = {
            "schema_version": "0.1",
            "provider": self.name,
            "normal": result.normal,
            "compact": result.compact,
        }
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
            self.stats.cache_writes += 1
        finally:
            if temporary.exists():
                temporary.unlink()
