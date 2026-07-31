import json

import httpx
import pytest

from papertrans.translation import (
    NonRetryableProviderError,
    RetryableProviderError,
    TranslationRequest,
)
from papertrans.translation.compatible_client import ChatCompletionsTranslationProvider
from papertrans.translation.profiles import (
    DEEPSEEK_PROFILE,
    KIMI_PROFILE,
    compatible_profile,
)


def _provider(
    handler,
    *,
    profile=DEEPSEEK_PROFILE,
) -> ChatCompletionsTranslationProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ChatCompletionsTranslationProvider(
        profile=profile,
        api_key="sentinel-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
        max_output_tokens=800,
        http_client=client,
    )


def _success_response(*, usage: object | None = None) -> httpx.Response:
    payload: dict[str, object] = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "normal": "中文⟦PT0001⟧",
                            "compact": "短文⟦PT0001⟧",
                        },
                        ensure_ascii=False,
                    )
                },
                "finish_reason": "stop",
            }
        ]
    }
    if usage is not None:
        payload["usage"] = usage
    return httpx.Response(200, json=payload)


def test_client_posts_structured_non_thinking_request_and_parses_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return _success_response(
            usage={
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 40,
                "prompt_cache_miss_tokens": 60,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        )

    provider = _provider(handler)
    result = provider.translate(
        [
            TranslationRequest(
                segment_id="s1",
                text="Source ⟦PT0001⟧",
                protected_tokens=("⟦PT0001⟧",),
            )
        ]
    )[0]
    assert captured["authorization"] == "Bearer sentinel-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["stream"] is False
    assert payload["max_tokens"] == 800
    assert result.normal == "中文⟦PT0001⟧"
    assert result.compact == "短文⟦PT0001⟧"
    assert result.usage is not None
    assert result.usage.cached_input_tokens == 40
    assert result.usage.uncached_input_tokens == 60
    assert result.usage.estimated_cost == 0.000014112


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": 10},
        {"completion_tokens": 2},
        [],
        {"prompt_tokens": "10", "completion_tokens": 2},
        {"prompt_tokens": 10, "completion_tokens": True},
    ],
)
def test_present_malformed_usage_is_retryable(usage: object) -> None:
    provider = _provider(lambda request: _success_response(usage=usage))

    with pytest.raises(RetryableProviderError) as exc_info:
        provider.translate(
            [
                TranslationRequest(
                    segment_id="s1",
                    text="Source ⟦PT0001⟧",
                    protected_tokens=("⟦PT0001⟧",),
                )
            ]
        )

    assert exc_info.value.error_type == "invalid_usage"


def test_present_null_usage_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "normal": "中文⟦PT0001⟧",
                                    "compact": "短文⟦PT0001⟧",
                                },
                                ensure_ascii=False,
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": None,
            },
        )

    provider = _provider(handler)

    with pytest.raises(RetryableProviderError) as exc_info:
        provider.translate(
            [
                TranslationRequest(
                    segment_id="s1",
                    text="Source ⟦PT0001⟧",
                    protected_tokens=("⟦PT0001⟧",),
                )
            ]
        )

    assert exc_info.value.error_type == "invalid_usage"


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_permanent_http_status_is_non_retryable(status: int) -> None:
    provider = _provider(
        lambda request: httpx.Response(
            status,
            json={"error": {"message": "secret body"}},
        )
    )

    with pytest.raises(NonRetryableProviderError) as exc_info:
        provider.translate([TranslationRequest(segment_id="s1", text="source")])

    assert exc_info.value.http_status == status
    assert "secret body" not in str(exc_info.value)


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_temporary_http_status_is_retryable(status: int) -> None:
    provider = _provider(
        lambda request: httpx.Response(
            status,
            json={"error": {"message": "private"}},
        )
    )

    with pytest.raises(RetryableProviderError) as exc_info:
        provider.translate([TranslationRequest(segment_id="s1", text="source")])

    assert exc_info.value.http_status == status
    assert "private" not in str(exc_info.value)


@pytest.mark.parametrize("status", [300, 405, 409, 600])
def test_other_non_success_status_is_sanitized_non_retryable(status: int) -> None:
    provider = _provider(lambda request: httpx.Response(status, text="sensitive response"))

    with pytest.raises(NonRetryableProviderError) as exc_info:
        provider.translate([TranslationRequest(segment_id="s1", text="source")])

    assert exc_info.value.error_type == "provider_http_error"
    assert exc_info.value.http_status == status
    assert "sensitive response" not in str(exc_info.value)


@pytest.mark.parametrize(
    "exception",
    [
        httpx.ConnectError("offline"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_network_failures_are_retryable(exception: httpx.RequestError) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception

    with pytest.raises(RetryableProviderError) as exc_info:
        _provider(handler).translate([TranslationRequest(segment_id="s1", text="source")])

    assert exc_info.value.error_type == "network_error"
    assert "offline" not in str(exc_info.value)
    assert "slow" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("response_payload", "error_type"),
    [
        ({"choices": []}, "missing_choices"),
        (
            {
                "choices": [
                    {
                        "message": {"content": '{"normal":"ok","compact":"ok"}'},
                        "finish_reason": "length",
                    }
                ]
            },
            "incomplete_response",
        ),
        (
            {
                "choices": [
                    {"message": {"content": ""}, "finish_reason": "stop"}
                ]
            },
            "empty_response",
        ),
        (
            {
                "choices": [
                    {"message": {"content": "not-json"}, "finish_reason": "stop"}
                ]
            },
            "invalid_json_response",
        ),
        (
            {
                "choices": [
                    {
                        "message": {"content": '{"normal":4,"compact":"ok"}'},
                        "finish_reason": "stop",
                    }
                ]
            },
            "invalid_translation_fields",
        ),
        (
            {
                "choices": [
                    {
                        "message": {"content": '{"normal":" ","compact":"ok"}'},
                        "finish_reason": "stop",
                    }
                ]
            },
            "empty_translation_fields",
        ),
    ],
)
def test_malformed_paid_response_is_retryable_with_usage(
    response_payload: dict[str, object],
    error_type: str,
) -> None:
    response_payload["usage"] = {
        "prompt_tokens": 10,
        "completion_tokens": 2,
        "total_tokens": 12,
    }
    provider = _provider(lambda request: httpx.Response(200, json=response_payload))

    with pytest.raises(RetryableProviderError) as exc_info:
        provider.translate([TranslationRequest(segment_id="s1", text="source")])

    assert exc_info.value.error_type == error_type
    assert exc_info.value.usage is not None
    assert exc_info.value.usage.input_tokens == 10
    assert exc_info.value.usage.output_tokens == 2


def test_placeholder_precheck_is_retryable_for_each_translation_variant() -> None:
    response = _success_response()
    provider = _provider(lambda request: response)

    with pytest.raises(RetryableProviderError) as exc_info:
        provider.translate(
            [
                TranslationRequest(
                    segment_id="s1",
                    text="Source ⟦PT0001⟧ ⟦PT0002⟧",
                    protected_tokens=("⟦PT0001⟧", "⟦PT0002⟧"),
                )
            ]
        )

    assert exc_info.value.error_type == "placeholder_validation_error"


@pytest.mark.parametrize(
    ("profile", "usage", "cached", "has_cost"),
    [
        (
            KIMI_PROFILE,
            {"prompt_tokens": 100, "cached_tokens": 25, "completion_tokens": 20},
            25,
            True,
        ),
        (
            compatible_profile("https://example.test/v1", "TEST_API_KEY"),
            {"prompt_tokens": 100, "completion_tokens": 20},
            0,
            False,
        ),
    ],
)
def test_usage_normalizes_provider_cache_fields(
    profile,
    usage,
    cached: int,
    has_cost: bool,
) -> None:
    result = _provider(
        lambda request: _success_response(usage=usage),
        profile=profile,
    ).translate(
        [
            TranslationRequest(
                segment_id="s1",
                text="Source ⟦PT0001⟧",
                protected_tokens=("⟦PT0001⟧",),
            )
        ]
    )[0]

    assert result.usage is not None
    assert result.usage.cached_input_tokens == cached
    assert result.usage.uncached_input_tokens == 100 - cached
    assert (result.usage.estimated_cost is not None) is has_cost


def test_cache_identity_excludes_credentials() -> None:
    provider = _provider(lambda request: _success_response())

    assert provider.cache_identity == DEEPSEEK_PROFILE.cache_identity("deepseek-v4-flash")
    assert "sentinel-key" not in json.dumps(provider.cache_identity)
