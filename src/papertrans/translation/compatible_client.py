from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from papertrans.translation.base import (
    TranslationRequest,
    TranslationResult,
    TranslationUsage,
)
from papertrans.translation.profiles import ProviderProfile
from papertrans.translation.prompt import build_chat_messages
from papertrans.translation.protection import placeholder_issues
from papertrans.translation.reliability import (
    NonRetryableProviderError,
    RetryableProviderError,
)

_PERMANENT_HTTP_STATUSES = frozenset({400, 401, 402, 403, 404, 422})


class ChatCompletionsTranslationProvider:
    def __init__(
        self,
        profile: ProviderProfile,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        http_client: httpx.Client | None,
    ) -> None:
        self.profile = profile
        self.name = profile.provider
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.cache_identity = profile.cache_identity(model)
        self._api_key = api_key
        self._http_client = http_client or httpx.Client()

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        return [self._translate_one(request) for request in requests]

    def _translate_one(self, request: TranslationRequest) -> TranslationResult:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": build_chat_messages(request),
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": self.max_output_tokens,
        }
        payload.update(_plain_mapping(self.profile.request_overrides))
        try:
            response = self._http_client.post(
                self.profile.chat_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.RequestError):
            raise RetryableProviderError(error_type="network_error") from None

        if not 200 <= response.status_code < 300:
            error = _http_error(response.status_code)
            raise error from None

        try:
            response_payload = response.json()
        except (json.JSONDecodeError, ValueError):
            raise RetryableProviderError(error_type="invalid_json_response") from None
        if not isinstance(response_payload, dict):
            raise RetryableProviderError(error_type="invalid_json_response")

        usage = _parse_usage(response_payload.get("usage"), self.profile)
        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RetryableProviderError(
                error_type="missing_choices",
                usage=usage,
            )
        choice = choices[0]
        if not isinstance(choice, dict):
            raise RetryableProviderError(
                error_type="missing_choices",
                usage=usage,
            )
        if choice.get("finish_reason") != "stop":
            raise RetryableProviderError(
                error_type="incomplete_response",
                usage=usage,
            )
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RetryableProviderError(
                error_type="empty_response",
                usage=usage,
            )
        try:
            translation = json.loads(content)
        except (json.JSONDecodeError, ValueError, TypeError):
            raise RetryableProviderError(
                error_type="invalid_json_response",
                usage=usage,
            ) from None
        if not isinstance(translation, dict):
            raise RetryableProviderError(
                error_type="invalid_translation_fields",
                usage=usage,
            )
        normal = translation.get("normal")
        compact = translation.get("compact")
        if not isinstance(normal, str) or not isinstance(compact, str):
            raise RetryableProviderError(
                error_type="invalid_translation_fields",
                usage=usage,
            )
        if not normal.strip() or not compact.strip():
            raise RetryableProviderError(
                error_type="empty_translation_fields",
                usage=usage,
            )
        if any(
            placeholder_issues(candidate, request.protected_tokens)
            != ((), (), ())
            for candidate in (normal, compact)
        ):
            raise RetryableProviderError(
                error_type="placeholder_validation_error",
                usage=usage,
            )
        return TranslationResult(
            segment_id=request.segment_id,
            normal=normal,
            compact=compact,
            provider=self.name,
            usage=usage,
        )


def _plain_mapping(mapping: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _plain_mapping(value) if isinstance(value, Mapping) else value
        for key, value in mapping.items()
    }


def _http_error(status: int) -> RetryableProviderError | NonRetryableProviderError:
    if status in _PERMANENT_HTTP_STATUSES:
        return NonRetryableProviderError(
            error_type="provider_http_error",
            http_status=status,
        )
    if status in {408, 429} or 500 <= status < 600:
        return RetryableProviderError(
            error_type="provider_http_error",
            http_status=status,
        )
    return NonRetryableProviderError(
        error_type="provider_http_error",
        http_status=status,
    )


def _parse_usage(raw_usage: object, profile: ProviderProfile) -> TranslationUsage | None:
    if raw_usage is None:
        return None
    if not isinstance(raw_usage, Mapping):
        raise RetryableProviderError(error_type="invalid_usage")
    if "prompt_tokens" not in raw_usage or "completion_tokens" not in raw_usage:
        raise RetryableProviderError(error_type="invalid_usage")
    input_tokens = _usage_integer(raw_usage, "prompt_tokens")
    output_tokens = _usage_integer(raw_usage, "completion_tokens")
    cached_input_tokens = 0
    if profile.provider == "deepseek":
        cached_input_tokens = _optional_usage_integer(
            raw_usage,
            "prompt_cache_hit_tokens",
        )
        if "prompt_cache_miss_tokens" in raw_usage:
            cache_miss_tokens = _usage_integer(raw_usage, "prompt_cache_miss_tokens")
            if cached_input_tokens + cache_miss_tokens != input_tokens:
                raise RetryableProviderError(error_type="invalid_usage")
    elif profile.provider == "kimi":
        cached_input_tokens = _optional_usage_integer(raw_usage, "cached_tokens")
    if "total_tokens" in raw_usage:
        total_tokens = _usage_integer(raw_usage, "total_tokens")
        if total_tokens != input_tokens + output_tokens:
            raise RetryableProviderError(error_type="invalid_usage")
    try:
        usage = TranslationUsage(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )
    except ValueError:
        raise RetryableProviderError(error_type="invalid_usage") from None
    if profile.pricing is None:
        return usage
    return TranslationUsage(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        estimated_cost=profile.pricing.estimate(usage),
        currency=profile.pricing.currency,
        pricing_snapshot=profile.pricing.snapshot,
    )


def _usage_integer(usage: Mapping[str, Any], field: str) -> int:
    value = usage[field]
    if type(value) is not int or value < 0:
        raise RetryableProviderError(error_type="invalid_usage")
    return value


def _optional_usage_integer(usage: Mapping[str, Any], field: str) -> int:
    if field not in usage:
        return 0
    return _usage_integer(usage, field)
